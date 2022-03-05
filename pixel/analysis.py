#!/usr/bin/env python
# --------------------------------------------------------
#       Main class for Rate Pixel Analysis
# created some time in 2016 by D.A. Sanz Becerra (sandiego@phys.ethz.ch), maintained by M. Reichmann (remichae@phys.ethz.ch)
# --------------------------------------------------------


from numpy import insert, sum as nsum, deg2rad, tan, rad2deg
from scipy.stats import poisson

from pixel.calibration import Calibration
from pixel.cut import PixCut
from pixel.run import PixelRun
from src.dut_analysis import *
from src.dut import Plane
from plotting.fit import Landau
import plotting.latex as latex


class PixAnalysis(DUTAnalysis):
    def __init__(self, run_number, dut, test_campaign=None, load_tree=True, verbose=False, prnt=True):

        DUTAnalysis.__init__(self, run_number, dut, test_campaign, load_tree, verbose, prnt)

        # Main
        self.N = self.dut_plane

        if self.Tree.Hash():
            self.Calibration = Calibration(self)
            self.Efficiency = self.make_eff()

        self.print_finished(prnt=prnt)

    def make_eff(self):
        from pixel.efficiency import Efficiency
        return Efficiency(self)

    # ----------------------------------------
    # region INIT
    @staticmethod
    def init_run(run_number, testcampaign, load_tree, verbose):
        return PixelRun(run_number, testcampaign, load_tree, verbose)

    def init_cut(self):
        return PixCut(self)

    def update_config(self):
        self.Config.read(join(self.Dir, 'config', self.TCString, 'PixelConfig.ini'))
    # endregion INIT
    # ----------------------------------------

    # ----------------------------------------
    # region DATA
    def get_data(self):
        e, n = eff2u(self.Efficiency.get()), ufloat(0, 0)
        return [self.get_flux(), self.get_current(), self.get_pulse_height(), e, n, e] + [n] * 3 + [ufloat(self.get_n_entries(), 0)]

    @quiet
    def save_plots(self, print_link=True):
        self.Efficiency.draw(show=False)
        self.Efficiency.draw_map(show=False)
        self.draw_occupancy(show=False)
        self.draw_correlation(show=False)
        super(PixAnalysis, self).save_plots(print_link)
    # endregion DATA
    # ----------------------------------------

    # ----------------------------------------
    # region GET
    @property
    def dut_plane(self):
        return self.DUT.Number + self.Run.NTelPlanes - 1

    def get_ph_var(self, plane=None, vcal=True):
        return f'cluster_charge[{choose(plane, self.N)}]{f" / {Bins.Vcal2El if vcal else 1e3}"}'

    def get_signal_var(self):
        return self.get_ph_var()

    @staticmethod
    def get_tp_var(dut: Any = True):
        return f'trigger_phase[{1 if dut else 0}]'

    @staticmethod
    def get_tp_vars():
        return [PixAnalysis.get_tp_var(dut=True), PixAnalysis.get_tp_var(dut=False)]

    @save_pickle('Fit', sub_dir='PH', suf_args='all')
    def _get_pulse_height(self, bin_size=None, cut=None, _redo=False):
        return self.draw_pulse_height(bin_size, cut, show=False)[1][0]

    @update_pbar
    def get_pulse_height(self, bin_size=None, cut=None, redo=False):  # copy required to mimic behaviour of pad method
        return self._get_pulse_height(bin_size, cut, _redo=redo)

    def get_vcal(self, redo=False):
        h = self.draw_vcal_distribution(show=False, redo=redo)
        return ufloat(h.GetMean(), h.GetMeanError())

    def get_nhits(self, cut=None):
        return self.get_tree_vec(f'n_hits[{self.N}]', self.Cut(cut), dtype='u2')

    def get_track_vars(self, mm=True, local=False, pixel=False):
        return self.Cut.get_track_vars(self.DUT.Number - 1, mm, local, pixel)

    def get_lambda(self, flux=None):
        """ :returns: lambda parameter of the poission distribution for a single clock cycle based on the flux"""
        return choose(flux, self.get_flux().n) * 1e3 * self.DUT.get_area() / self.Run.Plane.Frequency

    def get_efficiency(self, redo=False):
        return self.Efficiency.get(_redo=redo)
    # endregion GET
    # ----------------------------------------

    # ----------------------------------------
    # region OCCUPANCY
    def draw_occupancy(self, roc=None, name=None, cluster=True, tel_coods=False, cut='', **dkw):
        """ draw hitmap or cluster map """
        return self.Draw(self.Tel.draw_occupancy(choose(roc, self.N), choose(name, self.DUT.Name, roc), cluster, tel_coods, cut, show=False), **dkw)

    def draw_occupancy_trend(self, cut=None, fid=False, bin_size=None, **kwargs):
        cut = self.Cut.generate_custom(exclude='fiducial' if not fid else []) if cut is None else self.Cut(cut)
        x, y, zz = self.get_tree_vec([self.get_t_var()] + self.Tel.get_hit_vars(self.N), cut)
        h = self.Draw.histo_3d(x, y, zz, self.Bins.get_time(bin_size) + self.Bins.get_pixel(), y_tit='col', z_tit='row')
        x, px, py = get_3d_profiles(h, 'zy')
        y0, y1 = [[ufloat(ip.GetMean(), ip.GetMeanError()) for ip in p] for p in [px, py]]
        g = [self.Draw.graph(x, y, x_tit='Time [hh:mm]', y_tit='Mean Pixel Pos', show=False) for y in [y0, y1]]
        return self.Draw.multigraph(g, 'Hit Position Trend', ['Column', 'Row'], t_ax_off=0, **kwargs)

    def draw_n_tracks(self, flux=None, **dkw):
        """theoretical number of tracks through the DUT based on flux"""
        lam, x = self.get_lambda(flux), arange(1, 10)
        y = poisson.pmf(x - 1, lam) * 100
        self.Draw.graph(x, y, **prep_kw(dkw, x_range=[.5, where(y > 2e-10)[0][-1] + 1.5], y_range=[1e-10, 2e2], draw_opt='ab', x_tit='Number of Tracks', y_tit='Frequency [%]', logy=True, gridy=True))
    # endregion OCCUPANCY
    # ----------------------------------------

    # ----------------------------------------
    # region DISTRIBUTIONS
    def draw_adc_distribution(self, cut=None, col=None, row=None, pix=None, **dkw):
        x = self.get_tree_vec('adc', self.Cut(cut) + self.Cut.generate_masks(col, row, pix, exclude=False).Value + self.Cut.get_plane(), 'i2')
        return self.Draw.distribution(x, Bins.get_adc(), 'ADC Distribution', **prep_kw(dkw, x_tit='Pulse Height [adc]'))

    @save_pickle('VcalDisto', suf_args='all')
    def get_vcal_disto(self, cut=None, col=None, row=None, pix=None, vcal=True, _redo=False):
        cut = self.Cut(cut) + self.Cut.generate_masks(col, row, pix, exclude=False).Value + self.Cut.get_ncluster()
        n, v = self.get_nhits(cut), self.Calibration.get_vcals(*self.get_tree_vec(['col', 'row', 'adc'], cut + self.Cut.get_plane(), dtype='i2'))
        v = nsum(insert(v, cumsum(n).astype('i').repeat(max(n) - n), 0).reshape(n.size, max(n)), axis=1)  # fill arrays with zeros where there are less than max hits
        v *= (1 if vcal else Bins.Vcal2El)
        return self.Draw.distribution(v, title='Pulse Height Distribution', x_tit=f'Pulse Height [{"VCAL" if vcal else "e"}]', show=False)

    def draw_vcal_distribution(self, cut=None, col=None, row=None, pix=None, vcal=True, redo=False, **kwargs):
        h = self.get_vcal_disto(cut, col, row, pix, vcal, _redo=redo)
        return self.Draw.distribution(h, **kwargs, filename=f'PHDisto{"V" if vcal else "E"}')

    @save_pickle('PH', suf_args='all')
    def get_signal_disto(self, roc=None, cut=None, vcal=True, cutoff=None, _redo=False):
        x = self.get_tree_vec(self.get_ph_var(roc, vcal), self.Cut(cut))
        x = x[... if cutoff is None else x < cutoff]
        return self.Draw.distribution(x, find_bins(x, x0=0), title='Pulse Height Distribution', x_tit=f'Pulse Height [{"vcal" if vcal else "ke"}]', show=False)

    def draw_signal_distribution(self, roc=None, cut=None, vcal=True, redo=False, draw_thresh=False, fit=False, cutoff=False, **kwargs):
        h = self.get_signal_disto(roc, cut, vcal, cutoff, _redo=redo)
        t = self.draw_threshold(1500, 0, h.GetMaximum(), draw_thresh)
        self.info(f'Real MPV: {Landau(h, self.find_fit_range(h)).get_mpv(draw=True):.2f}') if fit else do_nothing()
        return self.Draw.distribution(h, **prep_kw(kwargs, x_range=ax_range(10, 10, fl=.2, fh=.5, h=h), leg=t, draw_opt='' if fit else None, file_name=f'SignalDistribution{"E" if not vcal else ""}'))

    @staticmethod
    def find_fit_range(h, fl=.5, fr=.2):
        xmax, ymax = find_mpv(h)
        x, y = get_hist_vecs(h, err=False)
        xr, yr = x[x > xmax], y[x > xmax]
        return [h.GetBinCenter(h.FindFirstBinAbove(fl * ymax.n)), xr[yr < fr * ymax.n][0]]

    def draw_map_disto(self, h, thresh=2, norm_x=False, **dkw):
        x = get_2d_hist_vec(h, err=False, zero_supp=False)[get_2d_bin_entries(h, flat=True) > thresh]
        x /= mean(x) if norm_x else 1
        return self.Draw.distribution(x, **prep_kw(dkw, normalise=True, stats=set_statbox(all_stat=True, form='.2f')))

    def draw_adc_map_disto(self, thresh=2, norm_x=False, **dkw):
        return self.draw_map_disto(self.draw_adc_map(show=False), thresh, norm_x, **prep_kw(dkw, x_tit=f'{"Normalised " if norm_x else ""}Pulse Height [adc]'))

    def draw_vcal_map_disto(self, thresh=2, norm_x=False, cutoff=None, **dkw):
        return self.draw_map_disto(self.draw_vcal_map(cutoff=cutoff, show=False), thresh, norm_x, **prep_kw(dkw, x_tit=f'{"Normalised " if norm_x else ""}Pulse Height [vcal]'))

    def draw_ncluster_disto(self, n=1, cut=None, redo=False, **kwargs):
        return self.draw_signal_distribution(cut=self.Cut.make(f'{n}cl', self.Cut(cut) + self.Cut.get_ncluster(n)), redo=redo, **kwargs)

    def draw_nhit_disto(self, n=1, cut=None, redo=False, **kwargs):
        return self.draw_signal_distribution(cut=self.Cut.make(f'{n}hit', self.Cut(cut) + self.Cut.get_ncluster(1) + self.Cut.get_nhit(n)), redo=redo, **kwargs)

    def draw_nhit_distos(self, nmax=4, cut=None, redo=False, **kwargs):
        h = [self.draw_nhit_disto(n, cut, redo, show=False) for n in range(1, nmax + 1)]
        return self.Draw.stack(h, 'NHit Distributions', ['1 hit'] + [f'{n} hits' for n in range(2, nmax + 1)], **kwargs)
    # endregion DISTRIBUTIONS
    # ----------------------------------------

    # ----------------------------------------
    # region PULSE HEIGHT
    def draw_pulse_height(self, bin_size=None, cut=None, **kwargs):
        """ Pulse height analysis vs event for a given cut. If no cut is provided it will take all. """
        x, y = self.get_tree_vec([self.get_t_var(), self.get_ph_var()], self.Cut(cut))
        bins = self.Bins.get_time(choose(bin_size, 1000 if y.size // 20 < 1000 or y.size / 1000 < 20 else y.size // 20))  # min bin size of 1000 max 20 points
        h = self.Draw.profile(x, y, bins, **prep_kw(kwargs, x_tit='Time [hh:mm]', y_tit='Pulse Height [vcal]', y_off=1.8, lm=.17, graph=True, stats=set_statbox(fit=True), t_ax_off=0))
        fit = FitRes(h.Fit('pol0', 'qs'))
        self.Draw.save_plots(f'PulseHeight{bin_size}')
        return h, fit

    def draw_signal_vs_trigger_phase(self, dut=True, cut=None, show=True):
        return super(PixAnalysis, self).draw_signal_vs_trigger_phase(dut, self.Cut.exclude('trigger_phase'), show)
    # endregion PULSE HEIGHT
    # ----------------------------------------

    # ----------------------------------------
    # region 2D DISTRIBUTIONS
    def draw_adc_map(self, cut=None, **dkw):
        x, y, zz = self.get_tree_vec(['col', 'row', 'adc'], self.Cut(cut) + self.Cut.get_plane())
        h = self.Draw.prof2d(x, y, zz, Bins.get_pixel(), show=False)
        e, v = get_2d_bin_entries(h, flat=True), get_2d_hist_vec(h, err=False, flat=True, zero_supp=False)
        return self.Draw.prof2d(h, **prep_kw(dkw, x_tit='Column', y_tit='Row', z_tit='Pulse Height [adc]', z_range=find_range(v[e > .1 * max(e)], .5, .5, .01)))

    def draw_vcal_map(self, cut=None, cutoff=None, **dkw):
        x, y, zz = self.get_tree_vec(self.Tel.get_hit_vars(self.N) + [self.get_ph_var()], self.Cut(cut))
        ecut = ... if cutoff is None else zz < cutoff
        h = self.Draw.prof2d(x[ecut], y[ecut], zz[ecut], Bins.get_pixel(), show=False)
        e, v = get_2d_bin_entries(h, flat=True), get_2d_hist_vec(h, err=False, flat=True, zero_supp=False)
        return self.Draw.prof2d(h, **prep_kw(dkw, x_tit='Cluster Column', y_tit='Cluster Row', z_tit='Pulse Height [vcal]', z_range=find_range(v[e > .1 * max(e)], .5, .5, .01)))

    def draw_adc_fixed_vcal_map(self, vcal=200, **kwargs):
        cols, rows = self.Cut.get_fid_lines()
        x, y, zz = array([[col, row, self.Calibration.get_adc(col, row, vcal)] for col in cols for row in rows]).T
        return self.Draw.prof2d(x, y, zz, Bins.get_pixel(), f'ADC Map (VCAL={vcal}', **prep_kw(kwargs, x_tit='col', y_tit='row', z_tit='ADC'))

    def draw_signal_map(self, *args, **kwargs):
        return super(PixAnalysis, self).draw_signal_map(*args, **prep_kw(kwargs, local=False, z_tit='Pulse Height [vcal]'))

    def draw_sig_map_disto(self, res=None, cut=None, fid=True, x_range=None, redo=False, normalise=False, ret_value=False, ph_bins=None, show=True, save=True):
        return super(PixAnalysis, self).draw_sig_map_disto(res, cut, fid, x_range, redo, normalise, ret_value, ph_bins=self.Bins.get_ph(), show=show, save=save)
    # endregion 2D DISTRIBUTIONS
    # ----------------------------------------

    # ----------------------------------------
    # region 3D
    def get_mod_vars(self, mx=1, my=1, ox=0, oy=0, zvar=None, cut=None, expand=True):
        x, y, z_ = self.get_tree_vec(self.get_track_vars(pixel=True) + [choose(zvar, self.get_ph_var())], self.Cut(cut))
        x, y, z_ = (x + ox / Plane.PX / 1e3) % mx, (y + oy / Plane.PY / 1e3) % my, z_
        return array(self.expand_mod_vars(x, y, z_, mx, my) if expand else (x, y, z_)) * [[Plane.PX * 1e3], [Plane.PY * 1e3], [1]]  # convert from pixel to um

    @staticmethod
    def expand_mod_vars(x, y, e, mx, my):
        d = array([x, y]).T
        (x, y), e = concatenate([d + [i, j] for i in [-mx, 0, mx] for j in [-my, 0, my]]).T, tile(e, 9)  # copy arrays in each direction
        cut = (x >= -mx / 2) & (x <= mx * 3 / 2) & (y >= -my / 2) & (y <= my * 3 / 2)  # select only half of the copied cells
        return x[cut], y[cut], e[cut]

    def draw_in(self, mx, my, ox=0, oy=0, nbins=None, cut=None, max_angle=None, zvar=None, **dkw):
        cut = self.Cut(cut) if max_angle is None else self.Cut.generate_custom(['track angle x', 'track angle y'], add=self.Cut.get_track_angle(max_angle), prnt=False)
        x, y, z_ = self.get_mod_vars(mx / Plane.PX * 1e-3, my / Plane.PY * 1e-3, ox, oy, zvar, cut)
        n = choose(nbins, freedman_diaconis, x=x) // 2 * 2  # should be symmetric...
        d = lambda w: round((n + .5) * (max(mx, my) / n - w) / w) * w  # extra spacing to account for different mx and my
        bins = sum([make_bins(-(i + w) / 2 - d(w), (3 * i + w) / 2 + d(w), w, last=True) for i, w in [(mx, mx / n), (my, my / n)]], start=[])
        cell = self.Draw.box(0, 0, mx, my, width=2, show=False, fillstyle=1)
        h = self.Draw.prof2d(x, y, z_, bins, title='Signal In Cell', x_tit='X [#mum]', y_tit='Y [#mum]', z_tit='Pulse Height [vcal]', show=False)
        return self.Draw(h, **prep_kw(dkw, leg=self.draw_columns(show=dkw['show'] if 'show' in dkw else True) + [cell]))

    def draw_ph_in_cell(self, nbins=None, ox=0, oy=0, cut=None, max_angle=None, **dkw):
        return self.draw_in(self.DUT.PX, self.DUT.PY, ox, oy, nbins, cut, max_angle, **prep_kw(dkw, pal=53))

    def draw_cs_in_pixel(self, nbins=None, ox=0, oy=0, cut=None, max_angle=None, **dkw):
        return self.draw_in(Plane.PX * 1e3, Plane.PY * 1e3, ox, oy, nbins, cut, max_angle, zvar=f'cluster_size[{self.N}]', **prep_kw(dkw, file_name='CSInPixel', z_tit='Cluster Size'))

    def draw_columns(self, show=True):
        if self.DUT.ColDia is not None:
            wx, wy, c = self.DUT.PX, self.DUT.PY, get_last_canvas()
            x0, x1, y0, y1 = c.GetUxmin(), c.GetUxmax(), c.GetUymin(), c.GetUymax()
            b = [Draw.circle(self.DUT.ColDia / 2, x, y, fill_color=602, fill=True, show=show) for x in arange(-2 * wx, x1, wx) for y in arange(-2 * wy, y1, wy) if x > x0 and y > y0]      # bias
            r = [Draw.circle(self.DUT.ColDia / 2, x, y, fill_color=799, fill=True, show=show) for x in arange(-2.5 * wx, x1, wx) for y in arange(-2.5 * wy, y1, wy) if x > x0 and y > y0]  # readout
            g = [Draw.make_tgrapherrors([1e3], [1e3], color=i, show=False, markersize=2) for i in [602, 799]]  # dummy graphs for legend
            return [Draw.legend(g, ['bias', 'readout'], 'p', y2=.82, show=show)] + b + r
        return []
    # endregion 3D
    # ----------------------------------------

    # ----------------------------------------
    # region THRESHOLD
    def draw_threshold(self, x=1500, y0=0, y1=1, show=True):
        if show:
            return self.Draw.y_axis(x, y0, y1, f'threshold #approx {x}e', off=.3, line=True, opt='-L')

    def draw_threshold_map(self, vcal=True, cols=None, rows=None, pix=None, **dkw):
        x, y, zz = self.Calibration.get_thresholds(cols, rows, pix, vcal).T
        return self.Draw.prof2d(x, y, zz, Bins.get_pixel(), 'Artificial Threshold Map', **prep_kw(dkw, x_tit='column', y_tit='row', z_tit=f'Threshold [{"vcal" if vcal else "ke"}]'))

    def draw_threshold_disto(self, vcal=True, **dkw):
        x = self.Calibration.get_thresholds(vcal=vcal).T[-1]
        return self.Draw.distribution(x, title='Threshold Distribution', **prep_kw(dkw, x_tit='Threshold [vcal]'))
    # endregion THRESHOLD
    # ----------------------------------------

    # ----------------------------------------
    # region TRIGGER PHASE
    def draw_trigger_phase(self, cut=None, **kwargs):
        self.Tel.draw_trigger_phase(dut=True, cut=cut, **kwargs)

    def draw_trigger_phase_offset(self, cut=None, **dkw):
        x, y = self.get_tree_vec(self.get_tp_vars(), choose(cut, self.Cut.generate_custom('trigger_phase', prnt=False)))
        return self.Draw.distribution(x - y, make_bins(-9.5, 10), **prep_kw(dkw, ndivx=20, x_tit='#Delta Trigger Phase', stats=set_entries()))

    def draw_tphase_offset_trend(self, bw=None, cut=None, **dkw):
        t, y0, y1 = self.get_tree_vec([self.get_t_var()] + self.get_tp_vars(), choose(cut, self.Cut.generate_custom('trigger_phase', prnt=False)))
        return self.Draw.profile(t, y0 - y1, self.Bins.get_time(bw, cut), 'Trigger Phase vs Time', **prep_kw(dkw, graph=True, y_tit='Trigger Phase', y_range=[-9, 9], **self.get_t_args()))

    def draw_tp_map(self, res=None, **dkw):
        x, y, zz = self.get_tree_vec(self.get_track_vars() + [self.get_tp_var()], cut=self.Cut.exclude('trigger_phase', 'fiducial'))
        self.Draw.prof2d(x, y, zz, Bins.get_global(res), 'TP Map', **prep_kw(dkw, **self.Tracks.ax_tits(), z_tit='Mean Trigger Phase'))

    def draw_single_tp_map(self, tp, res=None, **dkw):
        x, y = self.get_tree_vec(self.get_track_vars(), cut=self.Cut.generate_custom(['trigger_phase', 'fiducial'], add=f'trigger_phase == {tp}'))
        self.Draw.histo_2d(x, y, Bins.get_global(res), 'TP Map', **prep_kw(dkw, **self.Tracks.ax_tits(), z_tit='Mean Trigger Phase'))
    # endregion TRIGGER PHASE
    # ----------------------------------------

    # ----------------------------------------
    # region ALIGNMENT
    def get_alignment(self):
        from pixel.alignment import PixAlignment
        return PixAlignment

    def init_alignment(self, tel_plane=None, dut_plane=None):
        dut_plane = choose(dut_plane, self.dut_plane)
        if self.Alignment is None or self.Alignment.DUTPlane != dut_plane:
            self.Alignment = self.get_alignment()(self.Run.Converter, tel_plane, dut_plane)
        return self.Alignment

    def draw_correlation(self, tel_plane=None, dut_plane=None, offset=0, bin_size=1000, **dkw):
        self.Draw(self.init_alignment(tel_plane, dut_plane).draw_correlation(offset, bin_size, show=False), **prep_kw(dkw, y_range=[0, 1.15], file_name=f'Correlation{choose(dut_plane, self.N)}'))
    # endregion ALIGNMENT
    # ----------------------------------------

    # ----------------------------------------
    # region CLUSTER SIZE
    def get_cluster_size(self, cut=None, redo=False):
        return self.Tel.get_cluster_size(self.N, cut, _redo=redo)

    def draw_cluster_size(self, cut=None, **dkw):
        return self.Draw(self.Tel.draw_cluster_size(self.N, self.DUT.Name, self.Cut(cut), show=False), **dkw)

    def draw_cluster_size_vs_angle(self, **dkw):
        x, y, cs = self.get_tree_vec(['angle_x', 'angle_y', f'cluster_size[{self.N}]'], self.Cut.exclude('track angle x', 'track angle y'))
        self.Draw.prof2d(x, y, cs, **prep_kw(dkw, x_tit='Angle X', y_tit='Angle Y', z_tit='Cluster Size', z_range=[1, find_range(cs, q=.1)[-1]], file_name='CSAngle'))

    def draw_cluster_size_map(self, res=None, cut=None, pixel=True, fid=False, **dkw):
        x, y, z_ = self.get_tree_vec(self.get_track_vars(pixel=pixel and res is None) + [f'cluster_size[{self.N}]'], self.Cut.no_fid(fid, cut) + self.Cut.get_ncluster(1))
        h = self.Draw.prof2d(x, y, z_, **prep_kw({}, binning=find_2d_bins(x, y) if pixel and res is None else Bins.get_global(res), show=False))
        return self.Draw.prof2d(h, **prep_kw(dkw, **self.Tracks.ax_tits(pixel), z_tit='Cluster Size', leg=self.Cut.get_fid(), z_range=find_range(get_2d_hist_vec(h, err=False), 0, 0, .1), pal=53))
    # endregion CLUSTER SIZE
    # ----------------------------------------

    # ----------------------------------------
    # region DRAW
    def draw_detector_size(self):
        x, y = self.DUT.Size
        self.draw_size([x * Plane.PX, y * Plane.PY], color=432, name='detector')

    def draw_dut_hits(self, dut2=None, cut=None, **dkw):
        duts = [self.get_next_dut(dut2), self.DUT]
        x, y = self.get_tree_vec([f'n_hits[{dut.Number + self.Run.NTelPlanes - 1}]' for dut in duts], self.Cut(cut))
        x_tit, y_tit = [f'Number of Hits in {dut.Name}' for dut in duts]
        return self.Draw.histo_2d(x, y, [w for i in [x, y] for w in make_bins(*find_range(i, 0, 1.5))], **prep_kw(dkw, x_tit=x_tit, y_tit=y_tit, logz=True))

    def draw_hit_pie(self, dut2=None):
        duts = [self.get_next_dut(dut2), self.DUT]
        x, y = self.get_tree_vec([f'n_hits[{dut.Number + self.Run.NTelPlanes - 1}]' for dut in duts])
        labels = ['No Hits'] + [f'{dut.Name} Hit' for dut in duts] + ['Both Hits']
        e = [count_nonzero(i) for i in [(x == 0) & (y == 0), (x > 0) & (y == 0), (x == 0) & (y > 0), (x > 0) & (y > 0)]]
        self.Draw.pie(labels, e, offset=.05, h=.04, r=.2, text_size=.025, angle3d=70, angle_off=250, label_format='%txt (%perc)')

    def draw_residual(self, mode=None, cut=None, **dkw):
        return self.Tracks.draw_residual(self.N, mode=mode, cut=cut, **prep_kw(dkw, normalise=True))

    def get_residual(self, m='x', cut=None):
        return self.Tracks.get_residual_fit(self.N, m, cut)

    def print_residuals(self, tex=False):
        x, y = [self.get_residual(m) for m in ['x', 'y']]
        print(f'X Residual: {latex.si(x[0], fmt=".0f", unt="um")[0] if tex else f"{x[0]:.1f}"}, STD: {latex.si(x[1], fmt=".0f", unt="um")[0] if tex else f"{x[1]:.1f}"}')
        print(f'Y Residual: {latex.si(y[0], fmt=".0f", unt="um")[0] if tex else f"{y[0]:.1f}"}, STD: {latex.si(y[1], fmt=".0f", unt="um")[0] if tex else f"{y[1]:.1f}"}')

    def draw_xy_residual(self, f=.5, cut=None, show_cut=False, **dkw):
        return self.Draw.histo_2d(self.Tracks.draw_xy_residual(self.N, cut=self.Cut.exclude('rhit') if cut is None else self.Cut(cut), show=False, show_cut=show_cut, f=f), **dkw)

    def draw_alignment(self, bin_size=200, **kwargs):
        super(PixAnalysis, self).draw_alignment(bin_size, **kwargs)

    def draw_n_clusters(self, f=2, **dkw):
        return self.Draw(self.Tel.draw_n_clusters(self.N, self.DUT.Name, self.Cut.exclude('ncluster'), f, show=False), **prep_kw(dkw, logy=True, normalise=True))
    # endregion DRAW
    # ----------------------------------------

    def min_path(self, a):
        a, t, d, s = deg2rad(a), self.DUT.Thickness, self.DUT.ColDia, self.DUT.PX
        if not a:
            return 0
        l, l0 = t / cos(a), d / sin(a)
        if a < self.crit_angle(1):
            return max(0, l - l0) / t
        if a < self.crit_angle(1, s + d):
            l1 = (t * tan(a) - s) / sin(a)
            return (l - l0 - l1) / t
        if a < arctan(2 * s / t):
            return l - 2 * l0
        if a < arctan((2 * s + d) / t):
            l2 = (t * tan(a) - 2 * s) / sin(a)
            return l - 2 * l0 - l2
        if a < arctan(3 * s / t):
            return l - 3 * l0
        return 500

    def mpath(self, a, cols=1):
        # TODO: integrate over other direction ...
        a, t, d, s = deg2rad(a), self.DUT.Thickness, self.DUT.ColDia, self.DUT.PX
        l, xd = t / cos(a), max(d, t * tan(a))
        ld = min(l, d / sin(a)) * cols
        n = next(i for i in range(10) if a < self.crit_angle(i + 1))
        return ((l - n * ld) * (s - xd) + (l - (n + 1) * ld) * xd) / s

    def crit_angle(self, n=1, x=None):
        return arctan(n * choose(x, self.DUT.PX) / self.DUT.Thickness)

    def t(self, x, n):
        return rad2deg(self.crit_angle(n, x))

    def draw_crit_angles(self, n=4, **dkw):
        f = [Draw.make_tf1(None, self.t, 0, 160, n=i, color=self.Draw.get_color(n), npx=160) for i in arange(n) + 1]
        [self.Draw(i, draw_opt=o, **prep_kw(dkw, x_tit='Cell Size', y_tit='Rotation Angle', ndivx=503, grid=True)) for i, o in zip(reversed(f), [''] + ['same'] * 3)]
        Draw.legend(f, [f'n pixels = {i + 1}' for i in arange(n)], 'l', left=True)
        self.Draw.save_plots('CritAngles')

    def draw_mpath(self, max_a=30, cols=1):
        f = Draw.make_tf1('xpath', self.mpath, 0, max_a, npx=200, cols=cols)
        return self.Draw(f, x_tit='Rotation Angle', y_tit='Mean Path Length', file_name='MPath', y_range=[0, f.GetMaximum() * 1.1])

    def draw_min_path(self, max_a=5, **dkw):
        f = Draw.make_tf1('path', self.min_path, 0, max_a, npx=200)
        self.Draw(f, **prep_kw(dkw, x_tit='Rotation Angle', y_tit='Relative Minimum Path Length', file_name='MinPath', y_range=[0, 1.1], gridy=True))


if __name__ == '__main__':
    pargs = init_argparser(run=139, tc='201810', dut=1, has_verbose=True, tree=True)
    z = PixAnalysis(pargs.run, pargs.dut, pargs.testcampaign, pargs.tree)
