#!/usr/bin/env python
# --------------------------------------------------------
#       parent class for the analysis of a single device under test
# created on Oct 30th 2019 by M. Reichmann (remichae@phys.ethz.ch)
# --------------------------------------------------------

from numpy import vectorize, meshgrid, digitize, histogram2d, lexsort, invert, any
from numpy.random import rand
from uncertainties import umath

from src.currents import Currents
from src.cut import Cut
from src.run import Run
from src.tracks import Tracks
from src.telescope import Telescope
from helpers.save_plots import *
from src.analysis import Analysis
from helpers.fit import Langau
from src.binning import Bins
from functools import wraps


def reload_tree(func):
    @wraps(func)
    def my_func(*args, **kwargs):
        DUTAnalysis.reload_tree_(args[0])
        return func(*args, **kwargs)
    return my_func


class DUTAnalysis(Analysis):
    def __init__(self, run_number, diamond_nr=1, testcampaign=None, load_tree=None, verbose=False, prnt=True):

        self.Run = self.init_run(run_number, testcampaign, load_tree, verbose)
        self.DUT = self.Run.DUTs[diamond_nr - 1]
        super(DUTAnalysis, self).__init__(testcampaign, sub_dir=join(self.DUT.Name, str(self.Run.Number)), verbose=verbose)

        self.Tree = self.Run.Tree
        self.StartTime = self.Run.StartTime if self.Tree.Hash() else time_stamp(self.Run.LogStart)

        self.print_start(run_number, prnt, dut=self.DUT.Name)
        self.update_config()

        # Sub-Analyses
        self.Currents = Currents(self)

        if self.Tree.Hash():
            self.NRocs = self.Run.NPlanes
            self.Cut = self.init_cut()
            self.StartEvent = self.Cut.get_min_event()
            self.EndEvent = self.Cut.get_max_event()
            self.Bins = Bins(self)
            self.Tracks = Tracks(self)
            self.Tel = Telescope(self)

    def __str__(self):
        return f'{self.__class__.__name__} of {self.Run} and {self.DUT}'

    def __repr__(self):
        return self.__str__()

    def reload_tree_(self):
        self.Tree = self.Run.load_rootfile(prnt=False)

    def set_tree(self, tree):
        self.Tree = tree
        self.Run.Tree = tree

    @staticmethod
    def init_run(run_number, testcampaign, load_tree, verbose):
        return Run(run_number, testcampaign, load_tree, verbose)

    def init_cut(self):
        return Cut(self)

    def update_config(self):
        pass

    @staticmethod
    def get_info_header():
        return ['Run', 'Type', 'Diamond', 'Flux [kHz/cm2]', 'HV [V]']

    def show_information(self, header=True, prnt=True, ret_row=False):
        rows = [[self.Run.Number, self.Run.Info['runtype'], self.DUT.Name, '{:14.1f}'.format(self.Run.Flux.n), '{:+6.0f}'.format(self.DUT.Bias)]]
        return rows[0] if ret_row else print_table(rows, self.get_info_header() if header else None, prnt=prnt)

    def set_verbose(self, status: bool):
        self.Verbose = status
        for field in self.__dict__.values():
            if hasattr(field, 'Verbose'):
                field.Verbose = status

    # ----------------------------------------
    # region GET
    def has_branch(self, branch):
        return self.Run.has_branch(branch)

    def get_time(self):
        return self.Run.get_time()

    def get_track_vars(self, mm=True):
        return self.Cut.get_track_vars(self.DUT.Number - 1, mm)

    def get_t_var(self):
        return 'time / 1000.' if self.Run.TimeOffset is None else '(time - {}) / 1000.'.format(self.Run.TimeOffset)

    def get_eff_var(self, *args, **kwargs):
        return ''

    def get_t_off(self, rel_time):
        return self.Run.StartTime if rel_time else 0

    def get_t_args(self, rel_time=False):
        return {'x_tit': 'Time [hh::mm]', 't_ax_off': self.get_t_off(rel_time)}

    def get_tree_vec(self, var, cut='', dtype=None, nentries=None, firstentry=0):
        return self.Run.get_tree_vec(var, cut, dtype, nentries, firstentry)

    def get_events(self, cut=None, redo=False):
        if type(cut) == str:
            return self.get_tree_vec('Entry$', cut, dtype='i4')
        cut = self.Cut(cut)
        return do_hdf5(self.make_simple_hdf5_path('', cut.GetName(), 'Events'), self.get_tree_vec, redo, dtype='i4', var='Entry$', cut=cut) if cut.GetTitle() else arange(self.Run.NEvents)

    def get_event_cut(self, cut=None, redo=False):
        return self.make_event_cut(self.get_events(cut, redo))

    def set_event_cut(self, events):
        """ selects the [events] in the TTree, undo with self.reset_entries()"""
        from ROOT import TEntryList
        elist = TEntryList()
        for ev in array(events, 'i'):
            elist.Enter(ev)
        self.Tree.SetEntryList(elist)

    def reset_entries(self):
        """ reset the TEntryList from the TTree """
        self.Tree.SetEntryList(0)

    def make_event_cut(self, events):
        c = zeros(self.Run.NEvents, dtype=bool)
        c[events] = True
        return c

    def get_pulser_cut(self, inv=False):
        cut = self.make_event_cut(self.get_events(self.Cut['pulser']))
        return invert(cut) if inv else cut

    def get_sub_events(self, cut):
        e = array(self.get_events())
        s = array(self.get_events(cut))
        cut = zeros(self.Run.NEvents + 1, bool)
        cut[s] = True
        return cut[e]

    def get_event_at_time(self, seconds, rel=False):
        return self.Run.get_event_at_time(seconds, rel)

    def get_n_entries(self, cut=None):
        return self.Tree.GetEntries(self.Cut(cut).GetTitle())

    def get_current(self):
        return self.Currents.get_current()

    def get_irradiation(self):
        return self.DUT.get_irradiation(self.TCString)

    def get_attenuator(self):
        return False

    def get_ph_var(self, ped=False):
        return ''

    def get_pulse_height(self, *args, **kwargs):
        return ufloat(0, 0)

    def get_sm_data(self, cut=None, fid=False):
        """ :return: signal map data as numpy array [[x], [y], [ph]] with units [[mm], [mm], [mV]]
            :param cut: applies all cuts if None is provided.
            :param fid: return only values within the fiducial region set in the AnalysisConfig.ini"""
        cut = self.Cut.generate_custom(exclude=['fiducial'], prnt=False) if not fid and cut is None else self.Cut(cut)
        return self.get_tree_vec(self.get_track_vars() + [self.get_ph_var()], cut)

    def get_uniformity(self, use_fwc=True, redo=False):
        return do_pickle(self.make_simple_pickle_path('Uniformity', int(use_fwc), 'Signal'), self.draw_uniformity, redo=redo, show=False, use_fwc=use_fwc)

    def get_track_length_var(self):
        dx2, dy2 = ['TMath::Power(TMath::Tan(TMath::DegToRad() * {}_{}), 2)'.format('slope' if self.Run.has_branch('slope_x') else 'angle', direction) for direction in ['x', 'y']]
        return '{} * TMath::Sqrt({} + {} + 1)'.format(self.DUT.Thickness, dx2, dy2)

    def get_flux(self, plane=None, corr=True, full_size=False, show=False, redo=False):
        return self.Tel.get_flux(plane, corr, True, show, full_size, redo)

    def get_ph_values(self, *args, **kwargs):
        """ :returns: all pulse height values for a given cut. [numpy.ndarray] """

    def get_signal_name(self, *args, **kwargs):
        """ :returns: the pulse height variable in the tree. [str] """

    def get_signal_var(self, *args, **kwargs):
        """ :returns: the pulse height variable in the tree + corrections. [str] """

    def get_alignment(self, *args, **kwargs):
        return array([0, 1]), array([False])

    def get_split_ph(self, m=2):
        return get_2d_hist_vec(self.split_signal_map(m, show=0)[0])
    # endregion GET
    # ----------------------------------------

    # ----------------------------------------
    # region ALIASES
    def draw_chi2(self, *args, **kwargs):
        return self.Tracks.draw_chi2(*args, **kwargs)

    def draw_chi2s(self, *args, **kwargs):
        return self.Tracks.draw_chi2s(*args, **kwargs)

    def draw_angle(self, *args, **kwargs):
        return self.Tracks.draw_angle(*args, **kwargs)

    def draw_angles(self, *args, **kwargs):
        return self.Tracks.draw_angles(*args, **kwargs)

    def draw_occupancies(self, *args, **kwargs):
        return self.Tel.draw_occupancies(*args, **kwargs)

    def get_mean_angle(self, mode, redo):
        return self.Tracks.get_mean_angle(mode, redo)

    def draw_current(self, *args, **kwargs):
        return self.Currents.draw(*args, **kwargs)

    def draw_flux(self, *args, **kwargs):
        return self.Tel.draw_flux(*args, **kwargs)

    def draw_pulse_height(self, *args, **kwargs):
        return TProfile()

    def draw_signal_distribution(self, *args, **kwargs):
        pass

    def draw_fid_cut(self, scale=10):
        return self.Cut.draw_fid(scale)

    def check_alignment(self, redo):
        pass

    def get_efficiency(self, *args, **kwargs):
        pass
    # endregion ALIASES
    # ----------------------------------------

    # ----------------------------------------
    # region SIZES
    def draw_size(self, size=None, color=1, name=''):
        if size is None:
            return warning('The {} size of "{}" was not specified in the dia info'.format(' {}'.format(name) if name else '', self.DUT.Name))
        c = get_last_canvas()
        cx, cy = self.find_center()
        x, y = size
        c.cd()
        Draw.box(cx - x / 2, cy - y / 2, cx + x / 2, cy + y / 2, line_color=color, width=3, name=name, fillstyle=4000)

    def draw_detector_size(self):
        self.draw_size(self.DUT.Size, color=432, name='detector')

    def draw_metal_size(self):
        size = [self.DUT.PadSize.n] * 2 if self.DUT.PadSize is not None else None
        self.draw_size(size, color=923, name='metal')

    def draw_guard_ring(self):
        size = [self.DUT.GuardRing] * 2 if self.DUT.GuardRing is not None else None
        self.draw_size(size, color=417, name='guard ring')

    def draw_all_sizes(self):
        self.draw_fid_cut()
        self.draw_detector_size()
        self.draw_metal_size()
        self.draw_guard_ring()

    @save_pickle('Center', sub_dir='Maps')
    def find_center(self, _redo=False, h=None, _no_save=False):
        h = choose(h, self.get_signal_map(cut='', _redo=_redo))
        px, py = h.ProjectionX(), h.ProjectionY()
        return array([mean([p.GetBinCenter(b) for b in [p.FindFirstBinAbove(p.GetMaximum() * .5), p.FindLastBinAbove(p.GetMaximum() * .5)]]) for p in [px, py]])
    # endregion SIZES
    # ----------------------------------------

    # ----------------------------------------
    # region EFFICIENCY
    def draw_efficiency(self, bin_size=None, show=True):
        self.Draw.efficiency(*self.get_tree_vec([self.get_t_var(), self.get_eff_var()], self.Cut()), self.Bins.get_time(bin_size), show=show, **self.get_t_args())

    def draw_efficiency_map(self, res=None, n_sigma=4, cut=None, show=True):
        cut_string = choose(self.Cut(cut) + self.Cut.get('tracks'), self.Cut.generate_custom(exclude=['fiducial']), decider=cut)
        e, x, y = self.get_tree_vec(var=[self.get_eff_var(n_sigma)] + self.get_track_vars(), cut=cut_string)
        p = self.Draw.prof2d(x, y, e * 100, Bins.get_global(res), 'Efficiency Map', x_tit='X [cm]', y_tit='Y [cm]', z_tit='Efficiency [%]', ncont=100, z_range=[0, 100], show=show)
        set_2d_ranges(p, dx=3, dy=3)
        self.draw_fid_cut(scale=10)
        self.draw_detector_size()
        self.Draw.save_plots('EffMap')
    # endregion SIZES
    # ----------------------------------------

    def draw_alignment(self, bin_size=200, thresh=40, show=True):
        """ draw the aligment of telescope and DUT events """
        x, y = self.get_alignment(bin_size, thresh)
        h = TH2F('h{}'.format(self.Draw.get_count), 'Event Alignment', *(Bins.make(x) + [3, 0, 3]))
        for ibin, v in enumerate(y, 1):
            h.SetBinContent(ibin, 2, int(v) + 1)
        format_histo(h, x_tit='Event Number', y_tit='Alignment', stats=False, l_off_y=99, center_y=True)
        gStyle.SetPalette(3, array([1, 633, 418], 'i'))
        leg = Draw.make_legend(nentries=2, x2=.93, margin=.2)
        leg.AddEntry(Draw.box(0, 0, 0, 0, line_color=418, fillcolor=418, name='b1'), 'aligned', 'f')
        leg.AddEntry(Draw.box(0, 0, 0, 0, line_color=633, fillcolor=633), 'misaligned', 'f')
        self.Draw(h, 'EventAlignment', draw_opt='col', rm=.06, leg=leg, show=show, prnt=show)
        return h

    def draw_ph_pull(self, *args, **kwargs):
        return self._draw_ph_pull(*args, **kwargs)

    def _draw_ph_pull(self, evts_per_bin=None, fit=True, bin_width=.5, binning=None, show=True, save=True):
        p = self.draw_pulse_height(evts_per_bin, show=False, save=False)[0]
        h = Draw.pull(p, choose(binning, Bins.get_pad_ph(bin_width)), title=f'Signal Bin{Bins.get_size(evts_per_bin)} Distribution')
        format_histo(h, x_tit='Pulse Height [au]', y_tit='Entries', y_off=1.5, fill_color=Draw.FillColor, draw_first=True)
        set_statbox(all_stat=True, fit=fit)
        self.Draw(h, 'SignalBin{0}Disto'.format(Bins.get_size(evts_per_bin)), save=save, lm=.12, show=show, stats=True)
        return h

    def draw_track_length(self, show=True):
        h = TH1F('htd', 'Track Distance in Diamond', 200, self.DUT.Thickness, self.DUT.Thickness + 1)
        self.Tree.Draw('{}>>htd'.format(self.get_track_length_var()), 'n_tracks', 'goff')
        format_histo(h, x_tit='Distance [#mum]', y_tit='Entries', y_off=2, lw=2, stats=0, fill_color=Draw.FillColor, ndivx=405)
        self.Draw(h, show, lm=.16)
        return h

    def draw_signal_vs_angle(self, mode='x', bin_size=.1, show=True):
        p = TProfile('psa{}'.format(mode), 'Pulse Height vs. Angle in {}'.format(mode.title()), *self.Bins.get_angle(bin_size))
        self.Tree.Draw('{}:angle_{m}>>psa{m}'.format(self.get_signal_var(), m=mode), self.Cut(), 'goff')
        format_histo(p, x_tit='Track Angle [deg]', y_tit='Pulse Height [mV]', y_off=1.5)
        self.Draw(p, show=show, lm=.12, stats=set_entries())

    def draw_signal_vs_trigger_phase(self, dut=False, cut=None, show=True):
        x, y = self.get_tree_vec(['trigger_phase[{}]'.format([0, 1][dut]), self.get_signal_var()], self.Cut(cut))
        self.Draw.profile(x, y, make_bins(11), 'Signal vs. Trigger Phase', x_tit='Trigger Phase', y_tit='Pulse Height [mV]', show=show)

    # ----------------------------------------
    # region SIGNAL MAP
    @save_pickle('SM', sub_dir='Maps', print_dur=True, suf_args='all')
    def get_signal_map(self, res=None, cut=None, fid=False, ped=False, square=False, m=None, n=None, _redo=False):
        self.Tree.SetEstimate(self.Run.NEvents)
        v, bins = array(self.get_tree_vec(self.get_track_vars() + [self.get_ph_var(ped)])).T, Bins.get_global(res, square) if m is None else self.get_fid_bins(m, n)
        track_cut = self.get_event_cut(Cut.to_string(self.Cut.get('tracks')))
        c1 = self.get_event_cut(Cut.to_string(self.Cut.generate_custom(exclude='fiducial', prnt=False) if not fid and cut is None else self.Cut(cut)))[track_cut]
        c2 = c1 if fid else self.get_event_cut(Cut.to_string(self.Cut()))[track_cut]
        z_range = ax_range(get_2d_hist_vec(self.Draw.prof2d(*v[c2].T, bins, show=False)), thresh=4)
        return self.Draw.prof2d(*v[c1].T, bins, 'Pulse Height Map', x_tit='Track Position X [mm]', y_tit='Track Position Y [mm]', z_tit='Pulse Height [mV]', z_range=z_range, show=False, pal=53)

    def draw_signal_map(self, res=None, cut=None, fid=False, ped=False, square=False, m=None, n=None, scale=False, redo=False, **kwargs):
        h = self.get_signal_map(res, cut, fid, ped, square, m, n, _redo=redo)
        h.Scale(1 / self.get_pulse_height().n) if scale else do_nothing()
        rz = array([h.GetMinimum(), h.GetMaximum()]) * 1 / self.get_pulse_height().n if scale else None
        h = self.Draw.prof2d(h, **prep_kw(kwargs, centre=4, ncont=50, ndivy=510, ndivx=510, pal=53, z_tit='Relative Pulse Height' if scale else None, z_range=rz))
        if m is None:
            self.draw_fid_cut() if 'mirror' not in kwargs and 'rot' not in kwargs else do_nothing()
        self.Draw.save_plots('SignalMap2D', **prep_kw(kwargs, save=res is None and m is None and not scale))
        return h

    @save_pickle('HM', sub_dir='Maps', suf_args='all')
    def get_hitmap(self, res=None, cut='', _redo=False):
        x, y = self.get_tree_vec(self.get_track_vars(), self.Cut(cut))
        return self.Draw.histo_2d(x, y, Bins.get_global(res), 'Hit Map', x_tit='Track Position X [mm]', y_tit='Track Position Y [mm]', show=False)

    def draw_hitmap(self, res=None, cut='', redo=False, **kwargs):
        h = self.Draw.prof2d(self.get_hitmap(res, cut, _redo=redo), **prep_kw(kwargs, centre=4, title='DUT Hit Map'))
        self.draw_fid_cut()
        return h

    def get_fid_bins(self, m, n):
        n = choose(n, m)
        x, y = self.Cut.load_fiducial() * 10
        x_bins = linspace(x[0], x[2], m + 1)
        y_bins = linspace(y[0], y[2], n + 1)
        return [m, x_bins, n, y_bins]

    def get_fid_bin_events(self, m, n, mi, ni):
        m, x, n, y = self.get_fid_bins(m, n)
        cut = self.Cut.generate_sub_fid('f{}{}{}{}'.format(m, n, mi, ni), *array([x[mi], x[mi + 1], y[ni], y[ni + 1]]) / 10)
        return self.get_sub_events(cut)

    def split_signal_map(self, m=2, n=None, redo=False, draw_n=False, grid=True, **kwargs):
        h = self.draw_signal_map(fid=True, m=m, n=n, redo=redo, **prep_kw(kwargs, stats=False))
        Draw.grid(*get_2d_bins(h, arr=True), width=2) if grid else do_nothing()
        self.Draw.save_plots('SplitSigMap')
        Draw.bin_numbers(h, draw_n)
        return h

    def draw_split_means(self, n=10):
        x = arange(1, n + 1).tolist()
        y = [mean_sigma(get_2d_hist_vec(h))[0] for h in [self.split_signal_map(i, i, show=False)[0] for i in x]]
        self.Draw.graph(x, y, title='Split Means', x_tit='Division', y_tit='Pulse Height [mV]', draw_opt='ap')

    def get_ph_bins(self, n=10, pmin=90, pmax=95, show=True):
        h = self.split_signal_map(n, n, show=show, grid=False)[0]
        (x, y), v = get_2d_vecs(h)
        wx, wy = diff(x)[0] / 2, diff(y)[0] / 2
        points = array(meshgrid(x, y)).T[where((v >= pmin) & (v < pmax))]
        for ix, iy in points:
            Draw.box(ix - wx, iy - wy, ix + wx, iy + wy, line_color=840, width=4, show=show)
        return points, wx, wy

    def draw_ph_bin_disto(self, n=10, pmin=90, pmax=95, x_range=None, show=True):
        ph, x, y = self.get_tree_vec(var=[self.get_ph_var()] + self.get_track_vars(), cut=self.Cut())
        points, wx, wy = self.get_ph_bins(n, pmin, pmax, show=False)
        cut = any([(x > ix - wx) & (x < ix + wx) & (y > iy - wy) & (x < iy + wy) for ix, iy in points], axis=0)
        return self.Draw.distribution(ph[cut], self.Bins.get_pad_ph(mean_ph=mean(ph)), 'Pulse Height of Areas in [{}, {}] mV'.format(pmin, pmax), x_tit='Pulse Height [mV]', show=show, x_range=x_range)

    def draw_normal_distribution(self, m=20, n=30, show=True):
        ph, x, y = self.get_tree_vec(var=[self.get_ph_var()] + self.get_track_vars(), cut=self.Cut())
        ix, bx, iy, by = self.get_fid_bins(m, n)
        n = cumsum(histogram2d(x, y, [bx, by])[0].flatten().astype('i'))[:-1]  # get the number of events for each bin
        values = split(ph[lexsort((digitize(x, bx), digitize(y, by)))], n)  # bin x and y and sort then ph according to bins
        values = concatenate([lst / mean(lst) * mean(ph) for lst in values if lst.size > 2])  # normalise the values of each bin
        return self.Draw.distribution(values, self.Bins.get_pad_ph(mean_ph=mean(values)), 'Signal Distribution Normalised by area mean', x_tit='Pulse Height [mV]', show=show)

    def draw_sig_map_disto(self, res=None, cut=None, fid=True, x_range=None, redo=False, normalise=False, ret_value=False, ph_bins=None, show=True, save=True):
        x = get_2d_hist_vec(self.draw_signal_map(res, cut, fid, redo=redo, show=False), err=False) / (self.get_pulse_height() if normalise else 1)
        x_range = choose(x_range, ax_range(x, fl=.1, fh=.1))
        h = self.Draw.distribution(x, Bins.make(*x_range, n=sqrt(x.size)), 'Signal Map Distribution', x_tit='Pulse Height [mV]', y_off=2, lm=.15, show=show, save=save)
        return mean_sigma(x) if ret_value else h

    def draw_split_map_disto(self, m, n=None, x_range=None, fit=True, normalise=False, show=True):
        x = get_2d_hist_vec(self.split_signal_map(m, n, show=False)[0]) / (self.get_pulse_height() if normalise else 1)
        h = self.Draw.distribution(x, Bins.make(*choose(x_range, ax_range(x, 0, .1, .4, thresh=3)), n=sqrt(x.size)), 'Signal Map Distribution',
                                   x_tit='{}Pulse Height{}'.format(*['Normalised ', ''] if normalise else ['', ' [mV]']), show=show)
        h.Fit('gaus', 'qs{}'.format('' if fit else '0'))
        format_statbox(h, all_stat=True, fit=fit)
        return mean_sigma(x)

    def get_sm_std(self, res=None, redo=False):
        return self.draw_sig_map_disto(show=False, res=res, redo=redo, normalise=True, ret_value=True, save=False)[1]

    def draw_sm_profile(self, mode='x', factor=1.5, cut=None, fid=False, hitmap=False, redo=False, show=True):
        s = self.draw_signal_map(factor, cut, fid, hitmap=hitmap, redo=redo, show=False)
        g = Draw.make_tgrapherrors('g_smp', 'Signal Map Profile')
        values = [[] for _ in range(s.GetNbinsX() if mode == 'x' else s.GetNbinsY())]
        for xbin in range(s.GetNbinsX()):
            for ybin in range(s.GetNbinsY()):
                value = s.GetBinContent(xbin, ybin)
                if value:
                    values[(xbin if mode == 'x' else ybin)].append(value)
        for i, lst in enumerate(values):
            m, sigma = mean_sigma(lst) if lst else (0., 0.)
            xval = s.GetXaxis().GetBinCenter(i) if mode == 'x' else s.GetYaxis().GetBinCenter(i)
            g.SetPoint(i, xval, m)
            g.SetPointError(i, 0, sigma)

        format_histo(g, x_tit='Track in {m} [cm]'.format(m=mode), y_tit='Pulse Height [au]', y_off=1.5, ndivx=515)
        self.Draw(g, 'SignalMapProfile', draw_opt='ap', lm=.14, show=show, gridx=True)

    def draw_error_signal_map(self, show=True):
        h = self.draw_signal_map(show=False, fid=True).ProjectionXY('', 'c=e')
        format_histo(h, name='hsme', title='Signal Map Errors', y_off=1.6)
        self.Draw(h, 'SignalMapErrors', lm=.12, rm=.11, show=show, draw_opt='colz')
        return h

    def get_signal_spread(self, min_percent=5, max_percent=99, prnt=True):
        """ Calculates the relative spread of mean signal response from the 2D signal response map. """
        pickle_path = self.make_pickle_path('SignalMaps', 'Spread', self.Run.Number, self.DUT.Number)

        def f():
            h = self.draw_sig_map_disto(show=False)
            q = array([min_percent, max_percent]) / 100.
            y = zeros(2, 'd')
            mean_error = mean([v.n for v in get_2d_hist_vec(self.draw_error_signal_map(show=False))])
            h.GetQuantiles(2, y, q)
            return ufloat(y[1], mean_error) / ufloat(y[0], mean_error) - 1
        ratio = do_pickle(pickle_path, f)
        self.info('Relative Signal Spread is: {:2.2f} %'.format(ratio * 100), prnt=prnt)
        return ratio
    # endregion SIGNAL MAP
    # ----------------------------------------

    def draw_uniformity(self, histo=None, use_fwc=False, x_range=None, corr_noise=True, show=True, redo=False):
        noise = self.Pedestal.get_fwhm() if histo is None and hasattr(self, 'Pedestal') else 0
        h = self.draw_signal_distribution(show=show, normalise=True, redo=redo, x_range=x_range) if histo is None else histo
        (low, high), m = get_fwhm(h, ret_edges=True), get_fw_center(h) if use_fwc else ufloat(h.GetMean(), h.GetMeanError())
        Draw.vertical_line(m.n, 0, 1e7, style=7, w=2)
        fwhm, half_max = high - low, h.GetMaximum() / 2
        Draw.tlatex(m.n + 5, .1 * half_max, 'FWC' if use_fwc else 'Mean', align=10)
        Draw.arrow(low.n, m.n, half_max, half_max, col=2, width=3, opt='<', size=.02)
        Draw.arrow(high.n, m.n, half_max, half_max, col=2, width=3, opt='<', size=.02)
        Draw.tlatex(high.n + 5, half_max, 'FWHM', align=12, color=2)
        fwhm = umath.sqrt(fwhm ** 2 - noise ** 2) if corr_noise else fwhm
        value = fwhm / m
        legend = Draw.make_legend(w=.3, y2=.768, nentries=1, margin=.1, cols=2, scale=1.1)
        legend.AddEntry('', 'FWHM/{}'.format('FWC' if use_fwc else 'Mean'), '')
        legend.AddEntry('', '{:.2f} ({:.2f})'.format(value.n, value.s), '')
        legend.Draw()
        self.info('FWHM / MPV: {}'.format(value))
        h.Sumw2(False)
        update_canvas()
        return m, fwhm, value

    def model_trap_number(self, f=1000, t=1, max_traps=10000, steps=20, show=True):
        filled_traps = zeros(steps, dtype=int)
        decay = vectorize(self.decay)
        n_traps = []
        for i in range(steps):
            filled_traps[i] = f
            filled_traps = decay(filled_traps, t)
            n_traps.append(min(sum(filled_traps), max_traps))
        g = Draw.make_tgrapherrors(x=arange(steps), y=n_traps)
        format_histo(g, title='Number of Filled Traps', x_tit='Time [s]', y_tit='Number of Traps', y_off=1.7)
        self.Draw(g, draw_opt='ap', lm=.13, show=show)
        return n_traps[-1]

    def draw_n_traps(self, t=1, max_traps=1e5, nbins=20):
        x, y = log_bins(nbins, 100, 1e6)[1], []
        self.PBar.start(x.size)
        for f in x:
            y.append(self.model_trap_number(f, t, max_traps, show=False))
            self.PBar.update()
        g = Draw.make_tgrapherrors(x=x / 1000, y=y)
        format_histo(g, title='Number of Filled Traps vs Flux', x_tit='Flux [kHz/cm^{2}]', y_tit='Number of Filled Traps', y_off=1.7)
        self.Draw(g, draw_opt='ap', lm=.13, logx=True)

    @staticmethod
    def decay(n, t):
        return count_nonzero(rand(n) <= exp(-1. / t))

    def save_tree(self, cut=None):
        f = TFile('test.root', 'RECREATE')
        t = self.Tree.CloneTree(0)
        n = self.Tree.Draw('Entry$', self.Cut(cut), 'goff')
        good_events = self.Run.get_tree_vec(n, dtype='i4')
        self.PBar.start(n)
        for i, ev in enumerate(good_events):
            self.Tree.GetEntry(ev)
            t.Fill()
            self.PBar.update(i)
        f.cd()
        t.Write()
        macro = self.Run.RootFile.Get('region_information')
        if macro:
            macro.Write()
        f.Write()
        f.Close()
        self.info('successfully saved tree with only cut events.')

    def fit_langau(self, h=None, nconv=30, show=True, chi_thresh=8, fit_range=None):
        h = self.draw_signal_distribution(show=False) if h is None and hasattr(self, 'draw_signal_distribution') else h
        self.Draw.histo(h, show=show)
        fit = Langau(h, nconv, fit_range)
        fit.get_parameters()
        fit(show=show)
        update_canvas()
        if fit.get_chi2() > chi_thresh and nconv < 80:
            self.info('Chi2 too large ({c:2.2f}) -> increasing number of convolutions by 5'.format(c=fit.get_chi2()))
            fit = self.fit_langau(h, nconv + Draw.get_count('langau') * 5, chi_thresh=chi_thresh, show=show)
        print('MPV: {:1.1f}'.format(fit.get_mpv()))
        format_statbox(h, fit=True, all_stat=True)
        Draw.reset_count('langau')
        self.Draw.add(fit)
        return fit


if __name__ == '__main__':
    pargs = init_argparser(run=88, has_verbose=True, tree=True, dut=True)
    z = DUTAnalysis(pargs.run, pargs.dut, pargs.testcampaign, pargs.tree, verbose=True)
