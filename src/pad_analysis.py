from __future__ import print_function

from telescope_analysis import *
from json import loads
from ROOT import TH2I, TProfile2D, Double, TH2D
# from ROOT import TGraphErrors, TCanvas, TH2D, gStyle, TH1F, gROOT, TLegend, TCut, TGraph, TH2F, TProfile, TCutG, kGreen, TF1, THStack, TMultiGraph, Long, TH2I, gRandom, Double
from numpy import linspace
from uncertainties import umath

from CurrentInfo import Currents
from CutPad import CutPad
from Extrema import Extrema2D
from Peaks import PeakAnalysis
from Pedestal import PedestalAnalysis
from Pulser import PulserAnalysis
from Timing import TimingAnalysis
from converter import Converter
from waveform import Waveform


class PadAnalysis(TelecopeAnalysis):
    def __init__(self, run_number, diamond_nr, test_campaign=None, tree=None, verbose=False):

        TelecopeAnalysis.__init__(self, run_number, test_campaign, tree=tree, verbose=verbose)

        # Main Fields
        self.DiamondNumber = self.load_diamond_nr(diamond_nr)
        self.Channel = self.Run.Channels[diamond_nr - 1]
        self.DiamondName = self.Run.DiamondNames[diamond_nr - 1]
        self.Bias = self.Run.Bias[diamond_nr - 1]
        self.DigitiserBinWidth = .5 if self.Run.Digitiser == 'drs4' else .4

        # Config
        self.update_config()
        self.set_save_directory(join(self.DiamondName, str(self.RunNumber).zfill(3)))

        self.Currents = Currents(self)

        if self.Tree:
            self.Converter = Converter(self.Run)
            # Polarities
            self.Polarity = self.get_polarity()
            self.PulserPolarity = self.get_pulser_polarity()

            # Regions & Ranges
            self.IntegralNames = self.get_integral_names()
            self.IntegralRegions = self.load_regions()
            self.SignalRegionName = self.IntegralRegions['signal']
            self.SignalRegion = self.Run.IntegralRegions[self.DiamondNumber - 1][self.SignalRegionName]
            self.PedestalRegion = self.IntegralRegions['pedestal']
            self.PeakIntegralName = self.load_peak_integral()
            self.PeakIntegral = self.Run.PeakIntegrals[self.DiamondNumber - 1][self.PeakIntegralName]

            # Signal Names
            self.SignalDefinition = '({pol}*TimeIntegralValues[{num}])'
            self.SignalNumber = self.get_signal_number()
            self.SignalName = self.get_signal_name()
            self.PedestalName = self.get_pedestal_name()
            self.PeakName = self.get_peak_name()

            # cuts
            self.Timing = TimingAnalysis(self)
            self.Cut = CutPad(self, self.Channel)
            self.AllCuts = self.Cut.all_cut

            # subclasses
            self.Pulser = PulserAnalysis(self)
            self.Pedestal = PedestalAnalysis(self)
            self.Peaks = PeakAnalysis(self)
            self.Waveform = Waveform(self)

            # alignment
            self.IsAligned = self.check_alignment(show=False)

            self.Timing.reload_cut()

            self.print_finished()

    def draw_current(self, relative_time=False, averaging=1, show=True):
        self.Currents.draw_indep_graphs(rel_time=relative_time, averaging=averaging, show=show)

    def draw_timing(self):
        self.Timing.draw_all()

    def draw_pulser_rate(self, show=True, prnt=True):
        self.Pulser.draw_rate(show=show, prnt=prnt)

    # ----------------------------------------
    # region INIT
    def update_config(self):
        self.Config.read(join(self.Dir, 'Configuration', self.TCString, 'PadConfig.ini'))

    def load_diamond_nr(self, diamond_nr):
        if diamond_nr not in self.Run.DiamondNumbers:
            critical('wrong diamond number "{}". The following diamond numbers are valid: {}'.format(diamond_nr, self.Run.DiamondNumbers))
        return diamond_nr

    def get_short_regint(self, signal=None):
        return self.get_all_signal_names()[signal if signal is not None else z.SignalName]

    def get_integral_names(self):
        if self.Run.TreeConfig.has_section('Integral Names'):
            return [str(name) for name in loads(self.Run.TreeConfig.get('Integral Names', 'Names'))]
        self.Tree.GetEntry(0)
        return [str(name) for name in self.Tree.IntegralNames]

    def get_polarity(self):
        if not self.Run.TreeConfig.has_option('General', 'polarities'):
            warning('OLD DATA! Take polarities from config...')
            return loads(self.Run.Converter.load_polarities())[self.Channel]
        return int(self.Run.TreeConfig.get('General', 'polarities').split()[self.Channel])

    def get_pulser_polarity(self):
        if not self.Run.TreeConfig.has_option('General', 'pulser polarities'):
            warning('OLD DATA! Take pulser polarities from config...')
            return loads(self.Run.Converter.load_polarities(pulser=True))[self.Channel]
        return int(self.Run.TreeConfig.get('General', 'pulser polarities').split()[self.Channel])

    def load_regions(self):
        all_regions = {}
        for name in ['signal', 'pedestal', 'pulser']:
            option = '{} region'.format(name)
            region = '{name}_{region}'.format(name=name, region=self.Config.get('SIGNAL', option)) if option in self.Config.options('SIGNAL') else ''
            regions = [reg for reg in self.Run.IntegralRegions[self.DiamondNumber - 1] if reg.startswith(name)]
            all_regions[name] = region if region in regions else regions[0]
        return all_regions

    def load_peak_integral(self):
        peak_int = 'PeakIntegral{}'.format(self.Config.get('SIGNAL', 'peak integral'))
        return peak_int if peak_int in self.Run.PeakIntegrals[self.DiamondNumber - 1] else self.Run.PeakIntegrals[self.DiamondNumber - 1].keys()[0]

    def get_signal_number(self, region=None, peak_integral=None, sig_type='signal'):
        region = self.IntegralRegions[sig_type] if region is None else self.make_region(sig_type, region)
        peak_integral = self.PeakIntegralName if peak_integral is None else 'PeakIntegral{}'.format(peak_integral)
        int_name = 'ch{ch}_{reg}_{int}'.format(ch=self.Channel, reg=region, int=peak_integral)
        return self.IntegralNames.index(int_name)

    def get_signal_name(self, region=None, peak_integral=None, sig_type='signal'):
        num = self.get_signal_number(region, peak_integral, sig_type)
        return self.SignalDefinition.format(pol=self.Polarity, num=num)

    def get_signal_region(self, name=None):
        return self.Run.IntegralRegions[self.DiamondNumber - 1][self.SignalRegionName if name is None else 'signal_{}'.format(name)]

    def set_signal_definitions(self, use_time=True, sig_region=None, peak_int=None):
        signal = 'TimeIntegralValues' if use_time else 'IntegralValues'
        signal = '({{pol}}*{sig}[{{num}}])'.format(sig=signal)
        print('changed SignalDefinition to:', signal)
        self.SignalDefinition = signal
        self.update_signal_definitions(sig_region, peak_int)

    def update_signal_definitions(self, sig_region=None, peak_int=None):
        self.SignalNumber = self.get_signal_number(sig_region, peak_int)
        self.SignalName = self.get_signal_name(sig_region, peak_int)

    def get_pedestal_name(self, region=None, peak_int=None):
        return self.get_signal_name(region=region, peak_integral=peak_int, sig_type='pedestal')

    def get_peak_name(self, region=None, type_='signal', t_corr=True):
        peak_name = 'IntegralPeakTime' if t_corr else 'IntegralPeaks'
        return '{name}[{num}]'.format(name=peak_name, num=self.get_signal_number(region, None, type_))
    # endregion INIT
    # ----------------------------------------

    # ----------------------------------------
    # region GET
    def get_current(self):
        return self.Currents.get_current()

    def get_irradiation(self):
        return self.Run.get_irradiations()[self.DiamondNumber - 1]

    def get_attenuator(self):
        attenuators = self.Run.get_attenuators()
        return attenuators[self.DiamondNumber - 1] if attenuators else None

    def get_sm_data(self, cut=None, fid=False):
        """ :return: signal map data as numpy array [[x], [y], [ph]] with units [[mm], [mm], [mV]]
            :param cut: applies all cuts if None is provided.
            :param fid: return only values within the fiducial region set in the AnalysisConfig.ini"""
        x_var, y_var = (self.Cut.get_track_var(self.DiamondNumber - 1, v) for v in ['x', 'y'])
        cut = self.Cut.generate_special_cut(excluded=['fiducial'], prnt=False) if not fid and cut is None else cut
        cut = self.Cut.all_cut if cut is None else TCut(cut)
        n = self.Tree.Draw('{x}*10:{y}*10:{z}'.format(z=self.generate_signal_name(), x=x_var, y=y_var), cut, 'goff')  # *10 to get values in mm
        return self.Run.get_root_vecs(n, 3)

    def get_ph_data(self, cut=None):
        """ :return: pulse height data as numpy array [[time] [ph]] with units [[s], [mV]]
            :param cut: applies all cuts if None is provided."""
        cut_str = self.Cut.all_cut if cut is None else TCut(cut)
        n = self.Tree.Draw('time/1000.:{sig}'.format(sig=self.generate_signal_name()), cut_str, 'goff')
        return self.Run.get_root_vecs(n, 2)

    def get_pulse_height(self, bin_size=None, cut=None, redo=False, corr=True, sig=None):
        cut_str = self.Cut.all_cut if cut is None else TCut(cut)
        correction = '' if not corr else '_eventwise'
        suffix = '{bins}{cor}_{reg}{c}'.format(bins=self.Plots.BinSize if bin_size is None else bin_size, cor=correction, reg=self.get_short_regint(sig), c=cut_str.GetName())
        picklepath = self.make_pickle_path('Ph_fit', 'Fit', self.RunNumber, self.DiamondNumber, suf=suffix)

        def f():
            p, fit_pars = self.draw_pulse_height(bin_size=bin_size, cut=cut, corr=corr, show=False, save=False, redo=redo)
            return fit_pars

        return make_ufloat(do_pickle(picklepath, f, redo=redo), par=0)

    def get_results(self):
        return [self.get_pulse_height(), self.Pedestal.get_mean(), self.Pulser.get_pulse_height()]

    def print_results(self, prnt=True):
        rows = [[u_to_str(v, prec=2) for v in self.get_results()]]
        print_table(header=['Signal [mV]', 'Pedestal [mV]', 'Pulser [mV]'], rows=rows, prnt=prnt)
    # endregion GET
    # ----------------------------------------

    def make_all(self, redo=False):
        self.draw_signal_distribution(redo=redo, show=False)
        self.draw_pulse_height(redo=redo, show=False)
        self.draw_signal_map(redo=redo, show=False)
        self.draw_dia_hitmap(redo=redo, show=False)

    # ----------------------------------------
    # region 2D SIGNAL DISTRIBUTION
    def draw_efficiency_map(self, res=1.5, cut='all', show=True):
        cut_string = TCut(cut) + self.Cut.CutStrings['tracks']
        cut_string = self.Cut.generate_special_cut(excluded=['fiducial']) if cut == 'all' else cut_string
        p = TProfile2D('p_em', 'Efficiency Map {d}'.format(d=self.DiamondName), *self.Plots.get_global_bins(res, mm=True))
        y, x = self.Cut.get_track_vars(self.DiamondNumber - 1, scale=10)
        thresh = self.Pedestal.get_mean() * 4
        self.Tree.Draw('({s}>{t})*100:{y}:{x}>>p_em'.format(s=self.generate_signal_name(), x=x, y=y, t=thresh), cut_string, 'goff')
        self.format_statbox(n_entries=4, entries=True, x=.81)
        self.set_dia_margins(p)
        format_histo(p, x_tit='Track x [cm]', y_tit='Track y [cm]', z_tit='Efficiency [%]', y_off=1.4, z_off=1.5, ncont=100, z_range=[0, 100])
        self.draw_histo(p, show=show, lm=.13, rm=.17, draw_opt='colz', x=1.15 if self.Title else 1)
        self.draw_fiducial_cut(scale=10)
        self.draw_detector_size(scale=10)
        self.save_plots('EffMap')

    def draw_efficiency_vs_threshold(self, thresh=None, bin_width=.5, show=True):
        thresh = self.Pedestal.get_noise().n * 4 if thresh is None else thresh
        h = self.draw_signal_distribution(show=False, bin_width=bin_width)
        bins = range(h.FindBin(0), h.FindBin(thresh) + 2)
        err = Double()
        efficiencies = [make_ufloat(h.IntegralAndError(ibin, h.GetNbinsX(), err), err) / h.Integral() * 100 for ibin in bins]
        g = self.make_tgrapherrors('get', 'Detector Efficiency', x=[h.GetBinCenter(ibin) for ibin in bins], y=efficiencies)
        format_histo(g, x_tit='Threshold [mV]', y_tit='Efficiency [%]', y_off=1.3)
        self.draw_histo(g, draw_opt='ap', lm=.12, show=show)
        self.draw_vertical_line(x=self.Pedestal.get_noise().n * 3, ymin=0, ymax=110, w=2)
        self.draw_tlatex(x=self.Pedestal.get_noise().n * 3, y=95, text=' 3 #times noise', align=10)
        self.save_plots('EffThresh')

    def draw_signal_map(self, res=1.5, cut=None, fid=False, hitmap=False, redo=False, show=True, prnt=True, z_range=None, save=True, bins=None):
        cut = self.Cut.generate_special_cut(excluded=['fiducial'], prnt=prnt) if not fid and cut is None else cut
        cut = self.Cut.all_cut if cut is None else TCut(cut)
        suf = '{c}_{ch}_{res}'.format(c=cut.GetName(), ch=self.Cut.CutConfig['chi2X'], res=res if bins is None else '{}x{}'.format(bins[0], bins[2]))
        pickle_path = self.make_pickle_path('SignalMaps', 'Hit' if hitmap else 'Signal', run=self.RunNumber, ch=self.DiamondNumber, suf=suf)

        def func():
            set_root_output(0)
            name = 'h_hm' if hitmap else 'h_sm'
            atts = [name, 'Diamond Hit Map' if hitmap else 'Signal Map'] + (self.Plots.get_global_bins(res, mm=1) if bins is None else bins)
            h1 = TH2I(*atts) if hitmap else TProfile2D(*atts)
            self.info('drawing {mode}map of {dia} for Run {run}...'.format(dia=self.DiamondName, run=self.RunNumber, mode='hit' if hitmap else 'signal '), prnt=prnt)
            sig = self.generate_signal_name()
            x_var, y_var = (self.Cut.get_track_var(self.DiamondNumber - 1, v) for v in ['x', 'y'])
            self.Tree.Draw('{z}{y}*10:{x}*10>>{h}'.format(z=sig + ':' if not hitmap else '', x=x_var, y=y_var, h=name), cut, 'goff')
            return h1

        self.format_statbox(entries=True, x=0.82)
        gStyle.SetPalette(1 if hitmap else 53)
        h = do_pickle(pickle_path, func, redo=redo)
        self.set_dia_margins(h)
        self.adapt_z_range(h)
        z_tit = 'Number of Entries' if hitmap else 'Pulse Height [mV]'
        format_histo(h, x_tit='Track Position X [mm]', y_tit='Track Position Y [mm]', y_off=1.4, z_off=1.5, z_tit=z_tit, ncont=50, ndivy=510, ndivx=510, z_range=z_range)
        self.draw_histo(h, '', show, lm=.12, rm=.16, draw_opt='colzsame')
        self.draw_fiducial_cut(scale=10)
        # self.draw_detector_size(scale=10)
        self.save_plots('HitMap' if hitmap else 'SignalMap2D', prnt=prnt, save=save)
        return h

    def split_signal_map(self, m=2, n=2, grid=True, redo=False, show=True):
        fid_cut = array(self.Cut.CutConfig['fiducial']) * 10
        if not fid_cut.size:
            log_critical('fiducial cut not defined for {}'.format(self.DiamondName))
        x_bins = linspace(fid_cut[0], fid_cut[1], m + 1)
        y_bins = linspace(fid_cut[2], fid_cut[3], n + 1)
        bins = [m, x_bins, n, y_bins]
        h = self.draw_signal_map(bins=bins, show=False, fid=True, redo=redo)
        format_histo(h, x_range=[fid_cut[0], fid_cut[1] - .01], y_range=[fid_cut[2], fid_cut[3] - .01], name='hssm', stats=0)
        self.draw_histo(h, show=show, lm=.12, rm=.16, draw_opt='colzsame')
        self.draw_grid(x_bins, y_bins, width=2) if grid else do_nothing()
        self.save_plots('SplitSigMap')
        return h, x_bins, y_bins

    def draw_dia_hitmap(self, show=True, res=1.5, cut=None, fid=False, redo=False, prnt=True, z_range=None):
        h = self.draw_signal_map(show=False, res=res, cut=cut, fid=fid, hitmap=True, redo=redo, prnt=False, save=False)
        return self.draw_signal_map(show=show, res=res, cut=cut, fid=fid, hitmap=True, prnt=prnt, z_range=[0, h.GetMaximum()] if z_range is None else z_range)

    def draw_pedestal_map(self, high=10, low=None):
        low = '&&{}>{}'.format(self.generate_signal_name(), low) if low is not None else ''
        self.draw_dia_hitmap(redo=True, cut=TCut('{}<{}{}'.format(self.generate_signal_name(), high, low)) + self.Cut.generate_special_cut(excluded='fiducial'))

    @staticmethod
    def set_dia_margins(h, size=3):
        # find centers in x and y
        xmid, ymid = [(p.GetBinCenter(p.FindFirstBinAbove(0)) + p.GetBinCenter(p.FindLastBinAbove(0))) / 2 for p in [h.ProjectionX(), h.ProjectionY()]]
        format_histo(h, x_range=[xmid - size, xmid + size], y_range=[ymid - size, ymid + size])

    @staticmethod
    def adapt_z_range(h, n_sigma=2):
        bins = [i_bin for i_bin in xrange((h.GetNbinsX() + 2) * (h.GetNbinsY() + 2)) if h.GetBinContent(i_bin)]  # with overflow bins
        values = [h.GetBinContent(i_bin) for i_bin in bins]
        weights = [h.GetBinEntries(i_bin) for i_bin in bins] if hasattr(h, 'GetBinEntries') else None
        m, s = mean_sigma(values, weights)
        z_range = [min(values), 0.8 * max(values)] if s > m else [m - n_sigma * s, m + n_sigma * s]
        format_histo(h, z_range=z_range)

    def draw_sig_map_disto(self, show=True, factor=1.5, cut=None, fid=True, x_range=None, redo=False, normalise=False, ret_value=False, save=True):
        source = self.draw_signal_map(factor, cut, fid, hitmap=False, redo=redo, show=False, save=False)
        h = TH1F('h_smd', 'Signal Map Distribution', *([400, -50, 350] if not normalise else [400, 0, 4]))
        normalisation = 1 if not normalise else self.get_pulse_height()
        values = [make_ufloat((source.GetBinContent(ibin), 1)) / normalisation for ibin in xrange(source.GetNbinsX() * source.GetNbinsY()) if source.GetBinContent(ibin)]
        [h.Fill(v.n) for v in values]
        x_range = increased_range([h.GetBinCenter(ibin) for ibin in [h.FindFirstBinAbove(5), h.FindLastBinAbove(5)]], .3, .3) if x_range is None else x_range
        self.format_statbox(all_stat=True)
        format_histo(h, x_tit='Pulse Height [au]', y_tit='Number of Entries', y_off=2, fill_color=self.FillColor, x_range=x_range)
        self.save_histo(h, 'SignalMapDistribution', lm=.15, show=show, save=save)
        return mean_sigma(values) if ret_value else h

    def get_sm_std_dev(self, factor=3, redo=False):
        return self.draw_sig_map_disto(show=False, factor=factor, redo=redo, normalise=True, ret_value=True, save=False)[1]

    def draw_sig_map_profiles(self, mode='x', factor=1.5, cut=None, fid=False, hitmap=False, redo=False, show=True):
        s = self.draw_signal_map(factor, cut, fid, hitmap=hitmap, redo=redo, show=False)
        g = self.make_tgrapherrors('g_smp', 'Signal Map Profile')
        values = [[] for _ in xrange(s.GetNbinsX() if mode == 'x' else s.GetNbinsY())]
        for xbin in xrange(s.GetNbinsX()):
            for ybin in xrange(s.GetNbinsY()):
                value = s.GetBinContent(xbin, ybin)
                if value:
                    values[(xbin if mode == 'x' else ybin)].append(value)
        for i, lst in enumerate(values):
            m, sigma = mean_sigma(lst) if lst else (0., 0.)
            xval = s.GetXaxis().GetBinCenter(i) if mode == 'x' else s.GetYaxis().GetBinCenter(i)
            g.SetPoint(i, xval, m)
            g.SetPointError(i, 0, sigma)

        format_histo(g, x_tit='Track in {m} [cm]'.format(m=mode), y_tit='Pulse Height [au]', y_off=1.5, ndivx=515)
        self.save_histo(g, 'SignalMapProfile', draw_opt='ap', lm=.14, show=show, gridx=True)

    def make_region_cut(self):
        return self.Cut.generate_region(self.draw_signal_map(show=False), self.draw_sig_map_disto(show=False))

    def find_2d_regions(self):
        extrema = Extrema2D(self.draw_signal_map(show=False), self.draw_sig_map_disto(show=False))
        extrema.clear_voting_histos()
        extrema.region_scan()
        extrema.show_voting_histos()
        self.save_plots('Regions2D')
        return extrema

    def find_2d_extrema(self, size=1, histo=None, show=True):
        extrema = Extrema2D(self.draw_signal_map(show=False), self.draw_sig_map_disto(show=False))
        extrema.clear_voting_histos()
        extrema.square_scan(size, histo)
        if show:
            extrema.show_voting_histos()
        self.save_plots('Extrema2D')
        return extrema

    def draw_error_signal_map(self, show=False):
        h = self.draw_signal_map(show=False, fid=True).ProjectionXY('', 'c=e')
        if show:
            c = TCanvas('c', 'Signal Map Errors', 1000, 1000)
            c.SetLeftMargin(0.12)
            c.SetRightMargin(0.11)
            format_histo(h, name='sig_map_errors', title='Signal Map Errors', x_tit='track_x [cm]', y_tit='track_y [cm]', y_off=1.6)
            h.SetStats(0)
            h.Draw('colz')
            self.save_plots('SignalMapErrors', canvas=c)
            self.Objects.append([h, c])
        return h

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
        self.Objects.append(frame)

    def calc_signal_spread(self, min_percent=5, max_percent=99):
        """ Calculates the relative spread of mean signal response from the 2D signal response map. """
        h = self.draw_sig_map_disto(show=False)
        q = array([min_percent / 100., max_percent / 100.])
        y = array([0., 0.])
        h_e = self.draw_error_signal_map(show=False)
        e = mean([h_e.GetBinContent(i) for i in xrange(h_e.GetNbinsX() * h_e.GetNbinsY()) if h_e.GetBinContent(i)])
        h.GetQuantiles(2, y, q)
        max_min_ratio = (ufloat(y[1], e) / ufloat(y[0], e) - 1) * 100
        print('Relative Signal Spread is: {} %'.format(max_min_ratio))
        return max_min_ratio
    # endregion 2D SIGNAL DISTRIBUTION
    # ----------------------------------------

    # ----------------------------------------
    # region PULSE HEIGHT
    def generate_signal_name(self, signal=None, evnt_corr=True, off_corr=False, bin_corr=False, cut=None, region=None):
        sig_name = signal if signal is not None else self.get_signal_name(region)
        # pedestal polarity is always the same as signal polarity
        ped_pol = '1'
        # change polarity if pulser has opposite polarity to signal
        if hasattr(self, 'Pulser') and signal == self.Pulser.SignalName:
            ped_pol = '-1' if self.PulserPolarity != self.Polarity else ped_pol
        if bin_corr:
            return sig_name
        elif off_corr:
            sig_name += '-{pol}*{ped}'.format(ped=self.Pedestal.get_mean(cut).n, pol=ped_pol)
        elif evnt_corr:
            sig_name += '-{pol}*{ped}'.format(ped=self.PedestalName, pol=ped_pol)
        return sig_name

    def make_signal_time_histos(self, signal_name=None, evnt_corr=False, off_corr=False, bin_corr=False, rel_t=False, show=True):
        signal_name = self.generate_signal_name(self.SignalName if signal_name is None else signal_name, evnt_corr, off_corr, bin_corr)
        h = TH2D('h_st', 'Signal vs. Time', *(self.Plots.get_time_bins() + [225, -50, 500]))
        self.format_statbox(entries=True, x=.83)
        gStyle.SetPalette(53)
        self.Tree.Draw('{name}:time/1000>>h_st'.format(name=signal_name), self.Cut.all_cut, 'goff')
        format_histo(h, x_tit='Time [min]', y_tit='Pulse Height [au]', y_off=1.4, t_ax_off=self.Run.StartTime if rel_t else 0)
        self.save_histo(h, 'SignalTime', show, lm=.12, draw_opt='colz', rm=.15)
        return h

    def draw_pulse_height_vs_binsize(self, show=True):
        bin_sizes = [50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
        # pulse_heights = [make_ufloat(self.draw_pulse_height(binning=bin_size, show=False)[1], par=0) for bin_size in bin_sizes]
        pulse_heights = [make_ufloat(self.draw_ph(bin_size=bin_size, show=False)[1], par=0) for bin_size in bin_sizes]
        g = self.make_tgrapherrors('gdbs', 'Pulse Height vs Number of Events per Bin', x=bin_sizes, y=pulse_heights)
        format_histo(g, x_tit='Number of Events per Bin', y_tit='Pulse Height [mV]', y_off=1.2)
        self.draw_histo(g, lm=.12, show=show, gridy=True, logx=True)

    def draw_pulse_height(self, bin_size=None, cut=None, y_range=None, redo=False, corr=True, sig=None, rel_t=True, show=True, save=True, prnt=True):

        # TODO fix errors or extract from mean

        sig = self.SignalName if sig is None else sig
        correction = '' if not corr else '_eventwise'
        cut_str = self.Cut.all_cut if cut is None else TCut(cut)
        bin_size = self.Plots.BinSize if bin_size is None else bin_size
        suffix = '{bins}{cor}_{reg}{c}'.format(bins=bin_size, cor=correction, reg=self.get_short_regint(sig), c=cut_str.GetName())
        picklepath = self.make_pickle_path('Ph_fit', None, self.RunNumber, self.DiamondNumber, suf=suffix)

        def func():
            signal = self.generate_signal_name(self.SignalName if sig is None else sig, corr)
            prof = TProfile('pph', 'Pulse Height Evolution', *self.Plots.get_time_bins(bin_size))
            self.Tree.Draw('{sig}:time/1000.>>pph'.format(sig=signal), cut_str, 'goff')
            self.PulseHeight = prof
            return prof

        p = do_pickle(picklepath, func, redo=redo)
        self.format_statbox(n_entries=4, only_fit=True, w=.3)
        y_vals = [p.GetBinContent(i) for i in xrange(2, p.GetNbinsX() + 1)]
        format_histo(p, name='Fit Result', x_tit='Time [min]', y_tit='Mean Pulse Height [mV]', y_off=1.6, x_range=[self.Run.StartTime, self.Plots.get_time_bins()[1][-1]],
                     t_ax_off=self.Run.StartTime if rel_t else 0, y_range=increased_range([min(y_vals), max(y_vals)], .5, .5) if y_range is None else y_range, ndivx=505)
        self.draw_histo(p, show=show, lm=.14, prnt=save)
        fit = self.fit_pulse_height(p, picklepath)
        self.save_plots('PulseHeight{}'.format(bin_size), show=show, save=save, prnt=prnt)
        return p, fit

    def fit_pulse_height(self, p, picklepath):
        fit = p.Fit('pol0', 'qs', '', 0, self.__get_max_fit_pos(p))
        self.server_pickle(picklepath, FitRes(fit))
        return FitRes(fit)

    @staticmethod
    def __get_max_fit_pos(h):
        """ look for huge fluctiations in ph graph and return last stable point"""
        if mean([h.GetBinContent(i) for i in xrange(h.GetNbinsX())]) < 10:  # if the pulse height is very low there will be always big fluctuations!
            return h.GetBinCenter(h.GetNbinsX()) + 1000
        sum_ph = h.GetBinContent(1)
        for i in xrange(2, h.GetNbinsX() + 1):
            sum_ph += h.GetBinContent(i)
            if h.GetBinContent(i) < .7 * sum_ph / (i + 1):
                log_warning('Found huge ph fluctiation! Stopping Fit! y value = {y}, mean_y = {m}'.format(y=h.GetBinContent(i), m=sum_ph / (i + 1)))
                return h.GetBinCenter(i - 1)
        return h.GetBinCenter(h.GetNbinsX()) + 1000

    def draw_ph(self, bin_size=10000, y_range=None, rel_t=False, show=True):
        """ get pulse height by fitting every time bin disto with a Landau and then extrapolate with a pol0 """
        gr = self.make_tgrapherrors('hphl', 'Pulser Height Evolution')
        h = TH2F('tempph', '', *[v for bins in [self.Plots.get_time_bins(bin_size), self.Plots.get_ph_bins(bin_width=20)] for v in bins])
        self.Tree.Draw('{sig}:time/1000.>>tempph'.format(sig=self.SignalName), self.AllCuts, 'goff')
        i = 0
        for xbin in xrange(2, h.GetNbinsX() + 1):  # first bin is always empty
            py = h.ProjectionY('_py{}'.format(xbin), xbin, xbin)
            self.draw_histo(py)
            try:
                fit = self.fit_langau(py, nconv=50, show=True)
                raw_input()
                if fit.ParErrors[1] < .5:
                    continue
                gr.SetPoint(i, h.GetXaxis().GetBinCenter(xbin), fit.Parameters[1])
                gr.SetPointError(i, h.GetXaxis().GetBinWidth(xbin) / 2., fit.ParErrors[1])
                i += 1
            except ZeroDivisionError:
                pass
        self.format_statbox(only_fit=True)
        y_vals = [gr.GetY()[i] for i in xrange(gr.GetN())]
        format_histo(gr, x_tit='Time [min]', y_tit='Mean Pulse Height [au]', y_off=1.6, x_range=[self.Run.StartTime, self.Plots.get_time_bins()[1][-1]],
                     t_ax_off=self.Run.StartTime if rel_t else 0, y_range=increased_range([min(y_vals), max(y_vals)], .5, .5) if y_range is None else y_range, ndivx=505)
        fit = gr.Fit('pol0', 'qs')
        self.draw_histo(gr, draw_opt='ap', show=show)
        return gr, FitRes(fit)

    def draw_ph_distribution(self, binning=None, show=True, fit=True, xmin=0, xmax=270., bin_size=.5, save=True):
        self.Plots.set_bin_size(binning)
        sig_time = self.make_signal_time_histos(evnt_corr=True, show=False)
        if not show:
            gROOT.SetBatch(1)
        means = [h_proj.GetMean() for h_proj in [sig_time.ProjectionY(str(i), i + 1, i + 1) for i in xrange(self.Plots.NBins - 1)] if h_proj.GetEntries() > 10]
        nbins = int((xmax - xmin) / bin_size)
        h = TH1F('h', 'Signal Bin{0} Distribution'.format(self.Plots.BinSize), nbins, xmin, xmax)  # int(log(len(means), 2) * 2), extrema[0], extrema[1] + 2)
        for mean_ in means:
            h.Fill(mean_)
        format_histo(h, x_tit='Pulse Height [au]', y_tit='Entries', y_off=1.5, fill_color=407)
        h.Fit('gaus', 'q') if fit else do_nothing()
        if save:
            self.save_histo(h, 'SignalBin{0}Disto'.format(self.Plots.BinSize), lm=.12)
        return h

    def show_ph_overview(self, binning=None):
        self.draw_pulse_height(bin_size=binning, show=False)
        h1 = self.draw_pulse_height(show=False)[0]
        format_histo(h1, y_off=1.4)
        h2 = self.draw_ph_distribution(binning=binning, show=False)
        print(h1, h2)
        c = TCanvas('c', 'Pulse Height Distribution', 1500, 750)
        c.Divide(2, 1)
        for i, h in enumerate([h1, h2], 1):
            pad = c.cd(i)
            pad.SetBottomMargin(.15)
            h.Draw()
        self.save_plots('PHEvolutionOverview{0}'.format(self.Plots.BinSize))
        self.Objects.append([h2, c])

    def draw_signal_distribution(self, cut=None, evnt_corr=True, off_corr=False, show=True, sig=None, bin_width=.5, events=None,
                                 start=None, x_range=None, redo=False, prnt=True, save=True, normalise=None, sumw2=False):
        cut = self.AllCuts if cut is None else TCut(cut)
        suffix = '{b}_{c}_{cut}'.format(b=bin_width, c=int(evnt_corr), cut=cut.GetName())
        pickle_path = self.make_pickle_path('PulseHeight', 'Histo', run=self.RunNumber, ch=self.DiamondNumber, suf=suffix)

        def func():
            self.info('Drawing signal distribution for run {run} and {dia}...'.format(run=self.RunNumber, dia=self.DiamondName), prnt=prnt)
            set_root_output(False)
            h1 = TH1F('h_sd', 'Pulse Height {s}'.format(s='with Pedestal Correction' if evnt_corr else ''), *self.Plots.get_ph_bins(bin_width))
            sig_name = self.generate_signal_name(sig, evnt_corr, off_corr, False, cut)
            start_event = int(float(start)) if start is not None else 0
            n_events = self.Run.find_n_events(n=events, cut=str(cut), start=start_event) if events is not None else self.Run.NEntries
            self.Tree.Draw('{name}>>h_sd'.format(name=sig_name), str(cut), 'goff', n_events, start_event)
            h1.Rebin(max(1, int(h1.GetMean() / 30)))
            return h1

        self.format_statbox(all_stat=1, n_entries=5, w=.3)
        h = do_pickle(pickle_path, func, redo=redo)
        x_range = increased_range([h.GetBinCenter(i) for i in [h.FindFirstBinAbove(0), h.FindLastBinAbove(3)]], .1) if x_range is None else x_range
        format_histo(h, x_tit='Pulse Height [mV]', y_tit='Number of Entries', y_off=2, fill_color=self.FillColor, x_range=x_range, normalise=normalise)
        self.save_histo(h, 'SignalDistribution', lm=.15, show=show, prnt=prnt, save=save, sumw2=sumw2)
        return h

    def draw_signal_vs_peaktime(self, region=None, cut=None, show=True, corr=False, fine_corr=False, prof=True):
        suf = ' with {} Correction'.format('Fine' if fine_corr else 'Time') if corr else ''
        cut = self.Cut.all_cut if cut is None else cut
        x = self.get_signal_region(region)
        xbins = [(x[1] - x[0]) * (2 if corr else 1)] + list(array(x) * self.DigitiserBinWidth)
        h_args = ['hspt', 'Signal vs Peak Position{}'.format(suf)] + xbins + self.Plots.get_ph_bins()
        h = TProfile(*h_args[:5]) if prof else TH2F(*h_args)
        self.Tree.Draw('{}:{}>>hspt'.format(self.generate_signal_name(), self.Timing.get_peak_name(corr, fine_corr, region=region)), cut, 'goff')
        format_histo(h, x_tit='Signal Peak Position [ns]', y_tit='Pulse Height [mV]', y_off=1.4, stats=0)
        self.save_histo(h, 'SignalVsPeakPos{}{}'.format(int(corr), int(fine_corr)), show, lm=.11, draw_opt='' if prof else 'colz', rm=.03 if prof else .18)

    def draw_signal_vs_triggercell(self, bin_width=10, cut=None, show=True):
        p = TProfile('pstc', 'Signal vs. Trigger Cell', self.Run.NSamples / bin_width, 0, self.Run.NSamples)
        self.Tree.Draw('{}:trigger_cell>>pstc'.format(self.generate_signal_name()), self.Cut.all_cut if cut is None else TCut(cut), 'goff')
        format_histo(p, x_tit='Trigger Cell', y_tit='Pulse Height [au]', y_off=1.2, stats=0)
        self.save_histo(p, 'SignalVsTriggerCell', show, lm=.11)
    # endregion PULSE HEIGHT
    # ----------------------------------------

    # ----------------------------------------
    # region CUTS
    def show_bucket_histos(self):
        h = TH1F('h', 'Bucket Cut Histograms', 250, -50, 300)
        self.Tree.Draw('{name}>>h'.format(name=self.SignalName), '!({buc})&&{pul}'.format(buc=self.Cut.CutStrings['old_bucket'], pul=self.Cut.CutStrings['pulser']), 'goff')
        h1 = deepcopy(h)
        fit = self.Cut.fit_bucket(h1, show=False)
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
        self.save_plots('BucketHistos')
        self.Objects.append([h, h_sig, h_ped1, h_ped2, c])

    def show_bucket_numbers(self, show=True):
        pickle_path = self.PickleDir + 'Cuts/BucketEvents_{tc}_{run}_{dia}.pickle'.format(tc=self.TestCampaign, run=self.RunNumber, dia=self.DiamondName)

        def func():
            print('getting number of bucket events for run {run} and {dia}...'.format(run=self.RunNumber, dia=self.DiamondName))
            n_new = self.Tree.Draw('1', '!({buc})&&{pul}'.format(buc=self.Cut.CutStrings['bucket'], pul=self.Cut.CutStrings['pulser']), 'goff')
            n_old = self.Tree.Draw('1', '!({buc})&&{pul}'.format(buc=self.Cut.CutStrings['old_bucket'], pul=self.Cut.CutStrings['pulser']), 'goff')
            if show:
                print('New Bucket: {0} / {1} = {2:4.2f}%'.format(n_new, self.Run.NEntries, n_new / float(self.Run.NEntries) * 100))
                print('Old Bucket: {0} / {1} = {2:4.2f}%'.format(n_old, self.Run.NEntries, n_old / float(self.Run.NEntries) * 100))
            return {'old': n_old, 'new': n_new, 'all': float(self.Run.NEntries)}

        return do_pickle(pickle_path, func)

    def show_bucket_hits(self, show=True):
        # hit position
        h = TH2F('h', 'Diamond Margins', 80, -.3, .3, 52, -.3, .3)
        nr = 1 if not self.Channel else 2
        cut = '!({buc})&&{pul}'.format(buc=self.Cut.CutStrings['old_bucket'], pul=self.Cut.CutStrings['pulser'])
        self.Tree.Draw('dia_track_x[{nr}]:dia_track_y[{nr}]>>h'.format(nr=nr), cut, 'goff')
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
            print(zero_bins)
            c = TCanvas('c', 'Diamond Hit Map', 1000, 1000)
            h.GetXaxis().SetRangeUser(zero_bins[0][0], zero_bins[0][-1])
            h.GetYaxis().SetRangeUser(zero_bins[1][0], zero_bins[1][-1])
            h.Draw('colz')
            self.Objects.append([h, c])
        return h

    def draw_bucket_pedestal(self, show=True, corr=True, additional_cut=''):
        gStyle.SetPalette(55)
        # cut_string = self.Cut.generate_special_cut(included=['tracks', 'pulser', 'saturated'])
        cut_string = self.Cut.generate_special_cut(excluded=['bucket', 'timing'])
        cut_string += additional_cut
        self.draw_signal_vs_peaktime('e', cut_string, show, corr, fine_corr=corr, prof=False)
        self.save_plots('BucketPedestal')

    def draw_bucket_waveforms(self, show=True, t_corr=True, start=100000):
        good = self.Waveform.draw(1, show=False, start_event=None, t_corr=t_corr)[0]
        cut = self.Cut.generate_special_cut(excluded=['bucket', 'timing']) + TCut('!({0})'.format(self.Cut.CutStrings['bucket']))
        bucket = self.Waveform.draw(1, cut=cut, show=False, start_event=start, t_corr=t_corr)[0]
        cut = self.Cut.generate_special_cut(excluded=['bucket', 'timing']) + TCut('{buc}&&!({old})'.format(buc=self.Cut.CutStrings['bucket'], old=self.Cut.CutStrings['old_bucket']))
        bad_bucket = self.Waveform.draw(1, cut=cut, show=False, t_corr=t_corr, start_event=None)[0]
        self.reset_colors()
        mg = TMultiGraph('mg_bw', 'Bucket Waveforms')
        leg = self.make_legend(.85, .4, nentries=3)
        names = ['good wf', 'bucket wf', 'both wf']
        for i, gr in enumerate([good, bucket, bad_bucket]):
            format_histo(gr, color=self.get_color(), markersize=.5)
            mg.Add(gr, 'lp')
            leg.AddEntry(gr, names[i], 'lp')
        format_histo(mg, draw_first=True, x_tit='Time [ns]', y_tit='Signal [mV]')
        x = [self.Run.signal_regions['e'][0] / 2, self.Run.signal_regions['e'][1] / 2 + 20]
        format_histo(mg, x_range=x, y_off=.7)
        self.draw_histo(mg, show=show, draw_opt='A', x=1.5, y=0.75, lm=.07, rm=.045, bm=.2, leg=leg)
        # y = mg.GetYaxis().GetXmin(), mg.GetYaxis().GetXmax()
        # self._add_buckets(y[0], y[1], x[0], x[1], avr_pos=-1, full_line=True)
        self.save_plots('BucketWaveforms')
        self.reset_colors()

    def show_bucket_means(self, show=True, plot_histos=True):
        pickle_path = self.PickleDir + 'Cuts/BucketMeans_{tc}_{run}_{dia}.pickle'.format(tc=self.TestCampaign, run=self.RunNumber, dia=self.DiamondName)

        def func():
            gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
            cuts_nobucket = TCut('no_bucket', '')
            cuts_oldbucket = TCut('old_bucket', '')
            for key, value in self.Cut.CutStrings.iteritems():
                if not key.startswith('old') and key not in ['AllCuts', 'bucket']:
                    cuts_nobucket += value
                if key not in ['AllCuts', 'bucket']:
                    cuts_oldbucket += value
            h1 = self.draw_signal_distribution(show=False, evnt_corr=True)
            h2 = self.draw_signal_distribution(show=False, evnt_corr=True, cut=cuts_nobucket)
            h3 = self.draw_signal_distribution(show=False, evnt_corr=True, cut=cuts_oldbucket)
            if plot_histos:
                c = TCanvas('c', 'Bucket Histos', 1000, 1000)
                format_histo(h1, color=self.get_color(), lw=1, x_tit='Pulse Height [au]', y_tit='Entries')
                h1.Draw()
                format_histo(h2, color=self.get_color(), lw=1)
                h2.Draw('same')
                format_histo(h3, color=self.get_color(), lw=1)
                h3.Draw('same')
                self.Objects.append([h1, h2, h3, c])
            result = {name: [h.GetMean(), h.GetMeanError()] for name, h in zip(['new', 'no', 'old'], [h1, h2, h3])}
            gROOT.ProcessLine('gErrorIgnoreLevel = 0;')
            if show:
                print(result)
            return result

        res = func() if plot_histos else None
        return do_pickle(pickle_path, func, res)

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
                print('saving plot', key)
                save_name = 'signal_distribution_{cut}'.format(cut=key)
                histo_name = 'signal {range}{peakint}'.format(range=self.SignalRegionName, peakint=self.PeakIntegralName)
                histo_title = 'signal with cut ' + key
                histo = TH1F(histo_name, histo_title, 350, -50, 300)
                # safe single plots
                c1.cd()
                self.Tree.Draw("{name}>>{histo}".format(name=self.SignalName, histo=histo_name), value)
                self.save_plots(save_name)
                # draw all single plots into c2
                c2.cd()
                histo.SetLineColor(self.get_color())
                if not drawn_first:
                    format_histo(histo, title='Signal Distribution of Different Single Cuts', x_tit='Pulse Height [au]', y_tit='Entries', y_off=2)
                    histo.SetStats(0)
                    histo.Draw()
                    drawn_first = True
                else:
                    if key == 'AllCuts':
                        histo.SetLineWidth(2)
                    histo.Draw('same')
                histos.append(histo)
                legend.AddEntry(histo, key, 'l')
        # save c2
        legend.Draw()
        self.save_plots('all')
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
                histo_name = 'signal {range}{peakint}'.format(range=self.SignalRegionName, peakint=self.PeakIntegralName)
                histo_title = 'normalized' if not scale else 'scaled'
                histo_title += ' signal with cut ' + key
                histo = TH1F(histo_name, histo_title, 350, -50, 300)
                # safe single plots
                c1.cd()
                self.Tree.Draw("{name}>>{histo}".format(name=self.SignalName, histo=histo_name), value)
                if scale:
                    histo = scale_histo(histo, to_max=True)
                else:
                    histo = normalise_histo(histo, from_min=True, x_range=[0, 30])
                histo.Draw()
                c1.Update()
                self.save_plots(save_name)
                # draw all single plots into c2
                histo.SetLineColor(self.get_color())

                if key == 'AllCuts':
                    histo.SetLineWidth(2)
                stack.Add(histo)
                histos.append(histo)
                legend.AddEntry(histo, key, 'l')
        stack.Draw()
        gROOT.SetBatch(0)

        for h in histos:
            h.SetStats(False)
        name = '{0}Cuts'.format('Normalised' if not scale else 'Scaled')
        format_histo(stack, y_off=1.4, x_off=1.1)
        self.Objects.append(self.save_histo(stack, name, show, lm=.15, leg=legend, draw_opt='nostack'))
        gROOT.ProcessLine("gErrorIgnoreLevel = 0;")
        gROOT.SetBatch(0)

    def compare_consecutive_cuts(self, scale=False, show=True, save_single=True, short=False, x_range=None, redo=False):
        short_cuts = ['raw', 'saturated', 'timing', 'pulser', 'tracks', 'bucket', 'fiducial']
        legend = self.make_legend(.75 if short else .71, .88, nentries=len(self.Cut.ConsecutiveCuts) + 1 if not short else len(short_cuts) + 1, scale=.7)
        stack = THStack('scc', 'Signal Distribution with Consecutive Cuts')
        leg_style = 'l' if scale else 'f'
        for i, (key, cut) in enumerate(self.Cut.ConsecutiveCuts.iteritems()):
            if short and key not in short_cuts:
                continue
            self.info('adding cut {0}'.format(key))
            h = self.draw_signal_distribution(cut=cut, show=False, redo=redo)
            if scale:
                scale_histo(h, to_max=True, x_range=[30, 500])
            self.save_histo(h, 'signal_distribution_{n}cuts'.format(n=i), show=False, save=save_single)
            color = self.get_color()
            format_histo(h, color=color, stats=0, fill_color=color if not scale else None)
            stack.Add(h)
            leg_entry = '+ {0}'.format(key) if i else key
            legend.AddEntry(h, leg_entry, leg_style)
        if short:
            h = self.draw_signal_distribution(show=False, x_range=x_range)
            color = self.get_color()
            format_histo(h, color=color, stats=0, fill_color=color if not scale else None)
            stack.Add(h)
            legend.AddEntry(h, '+ other', leg_style)
        format_histo(stack, x_tit='Pulse Height [au]', y_tit='Number of Entries', y_off=1.9, draw_first=True)
        save_name = 'Consecutive{1}{0}'.format('Scaled' if scale else '', 'Short' if short else '')
        self.save_histo(stack, save_name, show, leg=legend, draw_opt='nostack', lm=0.14)
        stack.SetName(stack.GetName() + 'logy')
        # stack.SetMaximum(stack.GetMaximum() * 1.2)
        self.save_histo(stack, '{name}LogY'.format(name=save_name), show, logy=True, draw_opt='nostack', lm=0.14)
        self.reset_colors()

    def draw_fiducial_cut(self, scale=1):
        self.Cut.draw_fid_cut(scale)

    def draw_detector_size(self, scale=1):
        split_runs = self.Cut.get_fiducial_splits()
        first_cut_name = 'detector size' if self.Config.has_option('CUT', 'detector size') else 'detector size 1'
        values = next(self.Cut.load_dia_config('detector size {n}'.format(n=i + 1) if i else first_cut_name) for i in xrange(len(split_runs)) if self.RunNumber <= split_runs[i])
        if values is None:
            return
        x, y, lx, ly = values
        cut = TCutG('det{}'.format(scale), 5, array([x, x, x + lx, x + lx, x], 'd') * scale, array([y, y + ly, y + ly, y, y], 'd') * scale)
        cut.SetVarX(self.Cut.get_track_var(self.DiamondNumber - 1, 'x'))
        cut.SetVarY(self.Cut.get_track_var(self.DiamondNumber - 1, 'y'))
        self.Objects.append(cut)
        cut.SetLineWidth(3)
        cut.Draw()

    def draw_cut_means(self, show=True, short=False):
        gr = self.make_tgrapherrors('gr_cm', 'Mean of Pulse Height for Consecutive Cuts')
        gr.SetPoint(0, 0, 0)
        short_keys = ['raw', 'saturated', 'timing', 'bucket', 'pulser', 'tracks', 'fiducial']
        cuts = OrderedDict((key, item) for key, item in self.Cut.ConsecutiveCuts.iteritems() if not short or key in short_keys)
        for i, (key, cut) in enumerate(cuts.iteritems(), 1):
            self.info('adding cut {0}'.format(key))
            h = self.draw_signal_distribution(cut=cut, show=False)
            self.info('{0}, {1}, {2}'.format(key, h.GetMean(), h.GetMeanError()))
            gr.SetPoint(i, i, h.GetMean())
            gr.SetPointError(i, 0, h.GetMeanError())
        if short:
            h = self.draw_signal_distribution(show=False)
            gr.SetPoint(gr.GetN(), gr.GetN(), h.GetMean())
            gr.SetPointError(gr.GetN(), 0, h.GetMeanError())
        format_histo(gr, markersize=.2, fill_color=17, y_tit='Mean Pulse Height [au]', y_off=1.4)
        y = [gr.GetY()[i] for i in xrange(1, gr.GetN())]
        gr.GetYaxis().SetRangeUser(min(y) - 1, max(y) + 1)
        gr.GetXaxis().SetLabelSize(.05)
        for i in xrange(1, gr.GetN()):
            bin_x = gr.GetXaxis().FindBin(i)
            gr.GetXaxis().SetBinLabel(bin_x, cuts.keys()[i - 1])
        self.Objects.append(self.save_histo(gr, 'CutMeans{s}'.format(s='Short' if short else ''), show, bm=.25, draw_opt='bap', lm=.12, x=1.5))
        gROOT.ProcessLine('gErrorIgnoreLevel = 0;')

    def draw_distance_vs_ph(self, show=True, steps=10):
        h = self.draw_track_length(show=False, save=False)
        xmin, xmax = [h.GetBinCenter(i) for i in [h.FindFirstBinAbove(5), h.FindLastBinAbove(5)]]
        xvals = [xmin + i * (xmax - xmin) / steps for i in xrange(steps + 1)]
        gr = self.make_tgrapherrors('gr_aph', 'Pulse Height Vs Distance in Diamond')
        j = 0
        for i in xrange(len(xvals) - 1):
            cut = self.Cut.generate_distance(xvals[i], xvals[i + 1])
            self.Cut.all_cut += cut
            fit = self.draw_pulse_height(show=False)[1]
            if fit.Parameter(0):
                gr.SetPoint(j, xvals[i], fit.Parameter(0))
                gr.SetPointError(j, 0, fit.ParError(0))
                j += 1
            self.Cut.update_all_cut()
        self.draw_histo(gr, show)

    def test_landau_stats(self):
        gr = self.make_tgrapherrors('gr_ls', 'Landau Statistics')
        set_root_output(False)
        self.start_pbar(sum(int(pow(2, i / 2.)) for i in xrange(1, 40)))
        k = 0
        for j, i in enumerate(xrange(1, 40)):
            h = TH1F('h', 'h', 500, 0, 1000)
            for _ in xrange(int(pow(2, i / 2.))):
                k += 1
                h.Fill(gRandom.Landau(80, 5))
            self.ProgressBar.update(k)
            gr.SetPoint(j, pow(2, i), h.GetMean())
            gr.SetPointError(j, 0, h.GetMeanError())
        self.ProgressBar.finish()
        self.draw_histo(gr, draw_opt='alp', logx=True)

    def find_conv(self):
        gr = self.make_tgrapherrors('gr_c', 'chi2 vs nconv')
        for i, j in enumerate(xrange(10, 70, 5)):
            print(j)
            f = self.fit_langau(j, False)
            gr.SetPoint(i, j, f.Chi2 / f.NDF)
        self.draw_histo(gr)
    # endregion CUTS
    # ----------------------------------------

    # ----------------------------------------
    # region SHOW
    def draw_signal_vs_signale(self, show=True):
        gStyle.SetPalette(53)
        cut = self.Cut.generate_special_cut(excluded=['bucket'])
        num = self.get_signal_number(region='e')
        cut += TCut('IntegralPeakTime[{0}]<94&&IntegralPeakTime[{0}]>84'.format(num))
        h = TH2F('hsse', 'Signal b vs Signal e', 62, -50, 200, 50, 0, 200)
        self.Tree.Draw('{sige}:{sigb}>>hsse'.format(sigb=self.SignalName, sige=self.get_signal_name(region='e')), cut, 'goff')
        format_histo(h, x_tit='Signal s_b [au]', y_tit='Signal s_e [au]', z_tit='Number of Entries', z_off=1.1, y_off=1.5, stats=0)
        self.Objects.append(self.save_histo(h, 'SignalEvsSignalB', show, rm=.15, lm=.13, draw_opt='colz'))
        gStyle.SetPalette(1)
    # endregion
    # ----------------------------------------

    def check_alignment(self, n_pulser=200, thresh=40, show=True):
        """ just check the number of pixel hits at pulser events for no offset """
        pickle_path = 'Configuration/Individual_Configs/Alignment/{tc}_{run}.pickle'.format(tc=self.TestCampaign, run=self.Run.RunNumber)

        def f():
            xbins = self.Plots.get_pulser_bins(n_pulser)
            p = self.Pulser.draw_hit_efficiency(xbins, show=False)
            h = TH2F('ha{}'.format(self.RunNumber), 'Event Alignment', *(xbins + (3, 0, 3)))
            for ibin in xrange(5, xbins[0]):
                h.SetBinContent(ibin, 2, int(p.GetBinContent(ibin) <= thresh) + 1)
            format_histo(h, x_tit='Event Number', y_tit='Alignment', stats=False, l_off_y=99, center_y=True)
            gStyle.SetPalette(3, array([1, 2, 3], 'i'))
            leg = self.make_legend(nentries=2, x2=.9, margin=.2)
            leg.AddEntry(self.draw_box(0, 0, 0, 0, color=3, name='b1'), 'aligned', 'f')
            leg.AddEntry(self.draw_box(0, 0, 0, 0, color=2), 'misaligned', 'f')
            self.save_histo(h, 'EventAlignment', draw_opt='col', rm=.08, leg=leg, show=show, prnt=show)
            return sum(p.GetBinContent(bin_) > thresh for bin_ in xrange(5, p.GetNbinsX())) < p.GetNbinsX() * .05

        aligned = do_pickle(pickle_path, f, redo=show)
        log_warning('\nRun {r} is misaligned :-('.format(r=self.RunNumber)) if not aligned else do_nothing()
        return aligned

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
                print('process cut ' + key)
                # h = TH1F('h', '', 600, -100, 500)
                # self.Tree.Draw("{name}>>h".format(name=self.signal_name), value)
                h = self.draw_signal_distribution(evnt_corr=True, cut=value, show=False)
                i_mean = self.__get_mean(h)
                median = self.__get_median(h)
                mpv = self.__get_mpv(h)
                # print(mean, median, mpv)
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
        self.Objects.append(legend)
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

    def draw_snrs(self, show=True, lego=True, proj=False, draw_opt='lego2'):
        self.Verbose = False
        gStyle.SetPaintTextFormat('5.4g')
        lego = False if proj else lego
        gr = self.make_tgrapherrors('gr', 'Signal to Noise Ratios')
        h = TProfile2D('h_snr', 'Signal to Noise Ratios', 10, 0, 5, 10, 0, 5)
        i = 0
        for name, region in self.get_all_signal_names().iteritems():
            if self.SignalRegionName.split('_')[-1] in region:
                peak_integral = self.get_peak_integral(remove_letters(region))
                snr = self.calc_snr(name=name, reg=self.get_all_signal_names()[name])
                h.Fill(peak_integral[0] / 2., peak_integral[1] / 2., snr.n)
                gr.SetPoint(i, i + 1, snr.n)
                gr.SetPointError(i, 0, snr.s)
                gr.GetListOfFunctions().Add(self.draw_tlatex(i + 1, snr.n + snr.s * 1.5, str(peak_integral), align=22, size=.02))
                i += 1
        format_histo(gr, y_tit='SNR', y_off=1.2, color=self.get_color(), fill_color=1)
        vals = sorted([h.GetBinContent(i) for i in xrange(h.GetNbinsX() * h.GetNbinsY()) if h.GetBinContent(i)])
        x, y, z1 = Long(0), Long(0), Long(0)
        xmin, ymin = h.GetXaxis().GetXmin(), h.GetYaxis().GetXmin()
        h.GetBinXYZ(h.GetMaximumBin(), x, y, z1)
        x1, y1 = (x - 1) / 2. + xmin, (y - 1) / 2. + ymin
        self.__draw_profiles(h, x, y, proj)
        format_histo(h, x_tit='Left Length [ns]', x_off=1.45, y_tit='Right Length [ns]', y_off=1.6, z_tit='snr', z_off=1.6, stats=0, z_range=[vals[2], max(vals)])
        h.SetContour(50)
        gStyle.SetPalette(53)
        if draw_opt == 'coltext':
            self.show_best_snr(h, x1, y1, show)
        else:
            self.save_histo(h, 'SNRLego', show and lego, draw_opt=draw_opt, bm=.2, rm=.1, lm=.13, phi=-30, theta=40)
        gStyle.SetPalette(1)
        self.save_histo(gr, 'SNR', not (lego or proj) and show, draw_opt='bap')

    def show_best_snr(self, histo, x, y, show):
        h = histo
        format_histo(h, x_off=1, y_off=1.15, stats=0, z_tit='snr [au]', z_off=1.35)
        self.draw_histo(h, '', show, draw_opt='colztext', rm=.16)
        self.draw_vertical_line(x, -1e5, 1e5, color=2, style=2, name='a', w=2)
        self.draw_vertical_line(x + .5, -1e5, 1e5, color=2, style=2, name='b', w=2)
        self.draw_horizontal_line(y, 0, 10, color=418, style=2, w=2, name='c')
        self.draw_horizontal_line(y + .5, 0, 100, color=418, style=2, w=2, name='d')
        self.save_plots('SNRColText')

    def __draw_profiles(self, histo, x, y, show=True):
        h = histo
        py = h.ProfileY('Right Length', x, x)
        px = h.ProfileX('Left Length', y, y)
        vals = [py.GetBinContent(i) for i in xrange(py.GetNbinsX()) if py.GetBinContent(i)] + [px.GetBinContent(i) for i in xrange(px.GetNbinsX()) if px.GetBinContent(i)]
        format_histo(py, stats=0, lw=2)
        format_histo(px, stats=0, lw=2)
        py.SetLineColor(2)
        px.SetLineColor(418)
        leg = self.make_legend(.68, .95)
        [leg.AddEntry(p, p.GetName(), 'fp') for p in [py, px]]
        stack = THStack('s_sp', 'SNR Profiles')
        stack.Add(py, 'histe')
        stack.Add(px, 'histe')
        format_histo(stack, draw_first=True, x_tit='Integral Length [ns]', y_tit='snr [au]', y_off=1.35)
        stack.SetMinimum(increased_range([min(vals), max(vals)], .5, .5)[0])
        stack.SetMaximum(increased_range([min(vals), max(vals)], .5, .5)[1])
        self.save_histo(stack, 'SNRProfiles', show, draw_opt='nostack', leg=leg, lm=.13)

    def calc_snr(self, name=None, reg=''):
        signal_name = self.SignalName if name is None else name
        peak_int = remove_letters(self.get_all_signal_names()[signal_name])
        ped_sigma = make_ufloat(self.Pedestal.draw_disto_fit(save=False, name=self.Pedestal.get_signal_name(peak_int=peak_int), show=False), par=2)
        signal = make_ufloat(self.draw_pulse_height(corr=True, show=False, sig=signal_name)[1])
        snr = signal / ped_sigma
        print('{name} {0}\t| SNR is: {snr}\t {1} {2}'.format(self.get_peak_integral(peak_int), signal.n, ped_sigma.n, name=reg, snr=snr))
        return snr

    # ----------------------------------------
    # region PEAK INTEGRAL
    def find_best_snr(self, show=True, same_width=False):
        gROOT.SetBatch(1)
        gr = self.make_tgrapherrors('gr', 'Signal to Noise Ratios')
        peak_integrals = OrderedDict(sorted({key: value for key, value in self.Run.peak_integrals.iteritems() if len(key) < 3}.items()))
        i = 0
        for name, value in peak_integrals.iteritems():
            signal = self.get_signal_name('b', name)
            snr = self.calc_snr(signal)
            print(value)
            x = (value[1] + value[0]) / 2. if not same_width else value[0] / 2.
            gr.SetPoint(i, x, snr[0])
            gr.SetPointError(i, 0, snr[1])
            i += 1
        if show:
            gROOT.SetBatch(0)
        c = TCanvas('c', 'SNR', 1000, 1000)
        format_histo(gr, x_tit='Integralwidth [ns]', y_tit='SNR')
        gr.Draw('ap')
        gROOT.SetBatch(0)
        self.save_plots('BestSNR')
        self.Objects.append([gr, c])

    def signal_vs_peakintegral(self, show=True, ped=False):
        gROOT.SetBatch(1)
        gr = self.make_tgrapherrors('gr', '{sig} vs Peak Integral'.format(sig='Signal' if not ped else 'Pedestal'))
        peak_integrals = OrderedDict(sorted({key: value for key, value in self.Run.peak_integrals.iteritems() if len(key) < 3}.items()))
        i = 0
        ratio = '{0}{1}'.format(self.Run.peak_integrals.values()[0][0], self.Run.peak_integrals.values()[0][1])
        for name, value in peak_integrals.iteritems():
            sig_name = self.get_signal_name(region='b', peak_integral=name)
            signal = self.draw_pulse_height(corr=True, show=False, sig=sig_name) if not ped else self.Pedestal.draw_disto(save=False, name=self.Pedestal.get_signal_name(peak_int=name))
            par = 2 if ped else 0
            gr.SetPoint(i, (value[1] + value[0]) / 2., signal.Parameter(par))
            gr.SetPointError(i, 0, signal.ParError(par))
            i += 1
        if show:
            gROOT.SetBatch(0)
        c = TCanvas('c', 'Signal vs Peak Integral', 1000, 1000)
        format_histo(gr, x_tit='Integralwidth [ns]', y_tit='Signal [au]', y_off=1.3)
        gr.Draw('ap')
        gROOT.SetBatch(0)
        self.save_plots('{sig}PeakInt_{rat}'.format(rat=ratio, sig='Ped' if ped else 'Sig'))
        self.Objects.append([gr, c])
    # endregion PEAK INTEGRAL
    # ----------------------------------------

    # ----------------------------------------
    # region MISCELLANEOUS
    def get_all_signal_names(self, sig_type='signal'):
        names = OrderedDict()
        for region in self.Run.IntegralRegions[self.DiamondNumber - 1]:
            if sig_type in region:
                for integral in self.Run.PeakIntegrals[self.DiamondNumber - 1]:
                    name = 'ch{ch}_{reg}_{int}'.format(ch=self.Channel, reg=region, int=integral)
                    num = self.IntegralNames.index(name)
                    reg = region.replace(sig_type, '').strip('_') + integral.replace('PeakIntegral', '')
                    names[self.SignalDefinition.format(pol=self.Polarity, num=num)] = reg
        return names

    def print_information(self, header=True):
        header = ['Run', 'Type', 'Diamond', 'HV [V]', 'Region', 'Integral'] if header else None
        peak_int = '{} ({})'.format(self.PeakIntegral, remove_letters(self.PeakIntegralName))
        rows = [[self.RunNumber, self.Run.RunInfo['runtype'], self.DiamondName, self.Bias, '{} ({})'.format(self.SignalRegion, self.SignalRegionName.split('_')[-1]), peak_int]]
        print_table(rows, header)

    def show_integral_names(self):
        for i, name in enumerate(self.IntegralNames):
            if name.startswith('ch{}'.format(self.Channel)):
                print(str(i).zfill(3), name)
    # endregion MISCELLANEOUS
    # ----------------------------------------

    def draw_mpv_fwhm(self, histo=None, bins=10, show=True, redo=False):

        pickle_path = self.make_pickle_path('Signal', 'FWHMMPV', self.RunNumber, ch=self.DiamondNumber)

        def f(h=histo):
            fwhm_gauss = self.Pedestal.get_fwhm() if histo is None else 0
            h = self.draw_signal_distribution(show=show, normalise=True, sumw2=False, redo=redo) if h is None else h
            if histo is not None:
                self.draw_histo(h)
            sleep(.1)
            max_bin = h.GetMaximumBin()
            fit = TF1('fit', 'gaus', 10, 500)
            h.Fit('fit', 'qs', '', h.GetBinCenter(max_bin - bins), h.GetBinCenter(max_bin + bins))
            mpv = make_ufloat((fit.GetParameter(1), fit.GetParError(1) + fit.GetParameter(1) * .02))
            bin_width = h.GetBinWidth(1)
            half_max = fit(mpv.n) / 2
            x_fwhm_min, x_fwhm_max = (make_ufloat((h.GetBinCenter(i), bin_width)) for i in [h.FindFirstBinAbove(half_max), h.FindLastBinAbove(half_max)])
            fwhm_total = x_fwhm_max - x_fwhm_min
            self.draw_vertical_line(mpv.n, 0, 1e7, style=7, w=2)
            self.draw_tlatex(mpv.n + 5, .1 * half_max, 'MPV', align=10)
            self.draw_arrow(x_fwhm_min.n, mpv.n, half_max, half_max, col=2, width=3, opt='<', size=.02)
            self.draw_arrow(x_fwhm_max.n, mpv.n, half_max, half_max, col=2, width=3, opt='<', size=.02)
            self.draw_tlatex(x_fwhm_max.n + 5, half_max, 'FWHM', align=12, color=2)
            if mpv < 2 or fwhm_total < 1:
                log_warning('Could not determine fwhm or mpv')
                return None, None, None
            fwhm = umath.sqrt(fwhm_total ** 2 - fwhm_gauss ** 2)
            value = fwhm / mpv
            legend = self.make_legend(w=.3, y2=.78, nentries=1, margin=.1, cols=2, scale=1.1)
            legend.AddEntry('', 'FWHM/MPV', '')
            legend.AddEntry('', '{:.2f} ({:.2f})'.format(value.n, value.s), '')
            legend.Draw()
            self.info('FWHM / MPV: {}'.format(fwhm / mpv))
            h.Sumw2(False)
            get_last_canvas().Update()
            return mpv, fwhm, value

        return do_pickle(pickle_path, f, redo=redo or show) if histo is None else f()

    def get_peak_integral(self, name):
        return self.Run.PeakIntegrals[self.DiamondNumber - 1]['PeakIntegral{}'.format(name) if 'Peak' not in str(name) else name]

    @staticmethod
    def make_region(signal, region=''):
        return '{}{}'.format(signal, '_' + region if region else '')


if __name__ == '__main__':
    args = init_argparser(run=23, tc='201908', dia=1, tree=True, verbose=True)

    print()
    z = PadAnalysis(args.run, args.dia, args.testcampaign, args.tree, args.verbose)