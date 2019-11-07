from cut import Cut
from Extrema import Extrema2D
from functools import partial
from ROOT import TCut, TH1F, TF1, TCutG, TSpectrum
from utils import *
from json import loads
from numpy import array
from ConfigParser import NoOptionError
from draw import format_histo, fit_bucket


class CutPad(Cut):
    """The ChannelCut contains all cut settings which corresponds to a single diamond in a single run. """

    def __init__(self, analysis, channel=0):
        Cut.__init__(self, analysis, skip=True)
        self.__dict__.update(analysis.Cut.__dict__)
        self.channel = channel
        self.RunNumber = self.Analysis.RunNumber
        self.DUTName = analysis.DUTName
        self.DUTNumber = analysis.DUTNumber
        self.TCString = analysis.TCString

        self.load_channel_config()

        self.PedestalFit = None
        self.ped_range = None

        self.generate_channel_cutstrings()
        self.AllCut = self.generate_all_cut()
        self.CutStrings['AllCuts'] = self.AllCut

        self.ConsecutiveCuts = self.generate_consecutive_cuts()

    # ==============================================
    # region GET CONFIG
    def load_channel_config(self):
        self.CutConfig['absMedian_high'] = self.load_config_data('absolute median high')
        self.CutConfig['pedestalsigma'] = self.load_config_data('pedestal sigma')
        self.CutConfig['fiducial'] = self.load_fiducial()
        self.CutConfig['threshold'] = self.load_dia_config('threshold', store_true=True)

    def load_fiducial(self):
        first_cut_name = 'fiducial' if self.Config.has_option('CUT', 'fiducial') else 'fiducial 1'
        split_runs = self.get_fiducial_splits()
        return next(self.load_dia_config('fiducial {n}'.format(n=i + 1) if i else first_cut_name) for i in xrange(len(split_runs)) if self.RunNumber <= split_runs[i])

    def load_config_data(self, name):
        value = self.Config.get('CUT', name)
        return int(value) if value != 'None' else None

    def load_dia_config(self, name, store_true=False):
        try:
            conf = loads(self.Config.get('CUT', name))
            dia = self.Analysis.DUTName
            dia = '{}*{}'.format(dia, self.Analysis.DUTNumber) if '{}*1'.format(dia) in conf else dia
            if store_true:
                return dia in conf
            return conf[dia]
        except (KeyError, NoOptionError):
            log_warning('No option {0} in the analysis config for {1}!'.format(name, make_tc_str(self.TCString)))

    # endregion

    # ==============================================
    # region SET CUTS
    def set_cut(self, name, value=None):
        if name not in self.CutStrings:
            log_warning('There is no cut with the name "{name}"!'.format(name=name))
            return
        self.reset_cut(name)
        self.CutStrings[name] += self.generate_cut(name, value)
        self.update_all_cut()

    def set_abs_median_high(self, high=None):
        self.set_cut('median', high)

    def set_pedestal_sigma(self, sigma=None):
        self.set_cut('pedestalsigma', sigma)

    def set_signal_peak_pos(self, x_min, x_max):
        self.set_cut('signal_peak_pos', [x_min, x_max])

    def set_signal_peak_time(self, x_min, x_max):
        self.set_cut('signal_peak_time', [x_min, x_max])

    def set_trigger_cell(self, x_min, x_max):
        self.set_cut('trigger_cell', [x_min, x_max])

    def set_bucket(self, value):
        self.set_cut('bucket', value)
    # endregion

    # ==============================================
    # region GENERATE CUT STRINGS
    def generate_cut(self, name, value):
        dic = {'median': self.generate_median,
               'pedestalsigma': self.generate_pedestalsigma,
               'signal_peak_pos': self.generate_signal_peak_pos,
               'signal_peak_time': self.generate_signal_peak_time,
               'trigger_cell': self.generate_trigger_cell,
               'bucket': self.generate_bucket,
               'chi2X': partial(self.generate_chi2, 'x'),
               'chi2Y': partial(self.generate_chi2, 'y')}
        return dic[name](value)

    def generate_median(self, high=None):
        value = self.CutConfig['absMedian_high'] if high is None else high
        string = ''
        if value is not None:
            assert value > 0, 'The median has to be a positive number!'
            string = 'abs(median[{ch}])<{high}'.format(ch=self.channel, high=float(high))
            self.EasyCutStrings['absMedian_high'] = '|median|<{high}'.format(high=value)
        return TCut(string)

    def generate_pedestalsigma(self, sigma=None):
        sigma = self.CutConfig['pedestalsigma'] if sigma is None else sigma
        string = ''
        if sigma is not None:
            assert sigma > 0, 'The sigma has to be a positive number!'
            ped_range = self.__calc_pedestal_range(sigma)
            self.ped_range = ped_range
            string = '{ped}>{min}&&{ped}<{max}'.format(ped=self.Analysis.PedestalName, min=ped_range[0], max=ped_range[1])
            self.EasyCutStrings['pedestalsigma'] = 'PedSigma<{0}'.format(sigma)
        return TCut(string)

    def generate_region(self, signal_histo, mean_histo):
        extrema = Extrema2D(signal_histo, mean_histo)
        extrema.region_scan()
        extrema.show_voting_histos()
        all_string = ''
        nr = self.DUTNumber - 1
        for col in xrange(extrema.cols):
            all_val = [bool(extrema.VotingHistos['max'].GetBinContent(col, row)) for row in xrange(extrema.rows)]
            # print col, all_val
            if True not in all_val:
                continue
            all_string += '||' if all_string else ''
            xmin = extrema.VotingHistos['max'].GetXaxis().GetBinLowEdge(col)
            xmax = extrema.VotingHistos['max'].GetXaxis().GetBinUpEdge(col)
            all_string += '(dia_track_x[{nr}]>{xmin}&&dia_track_x[{nr}]<{xmax})&&'.format(nr=nr, xmin=xmin, xmax=xmax)
            y_string = ''
            cont = True
            for row in xrange(extrema.rows + 1):
                val = extrema.VotingHistos['max'].GetBinContent(col, row) if not row == extrema.rows else 0
                last_val = extrema.VotingHistos['max'].GetBinContent(col, row - 1) if row else 0
                if val and not last_val:
                    y = extrema.VotingHistos['max'].GetYaxis().GetBinLowEdge(row)
                    if y < abs(1e-10):
                        cont = False
                        continue
                    cont = True
                    y_string += '||' if y_string else '('
                    y_string += 'dia_track_y[{nr}]>{y}&&'.format(nr=nr, y=y)
                elif not val and last_val and cont:
                    y_string += 'dia_track_y[{nr}]<{y}'.format(nr=nr, y=extrema.VotingHistos['max'].GetYaxis().GetBinUpEdge(row))
            y_string += ')'
            all_string += y_string
        # self.region_cut += all_string ?
        return extrema

    def generate_signal_peak_pos(self, min_max):
        assert 0 <= min_max[0] <= 1024, 'min signal peak has to be in [0, 1024], not "{min}"'.format(min=min_max[0])
        assert 0 <= min_max[1] <= 1024, 'max signal peak has to be in [0, 1024], not "{max}"'.format(max=min_max[1])
        self.EasyCutStrings['SignalPeakPos'] = 'Signal Peak in {0}'.format(min_max)
        return TCut('IntegralPeaks[{num}] < {max} && IntegralPeaks[{num}] >= {min}'.format(num=self.Analysis.SignalNumber, min=min_max[0], max=min_max[1]))

    def generate_signal_peak_time(self, min_max):
        assert 0 <= min_max[0] <= 1024, 'min signal peak time has to be in [0, 1024], not "{min}"'.format(min=min_max[0])
        assert 0 <= min_max[1] <= 1024, 'max signal peak time has to be in [0, 1024], not "{max}"'.format(max=min_max[1])
        self.EasyCutStrings['SignalPeakTime'] = 'Signal Peak Time in {0}'.format(min_max)
        return TCut('IntegralPeakTime[{num}] < {max} && IntegralPeakTime[{num}] >= {min}'.format(num=self.Analysis.SignalNumber, min=min_max[0], max=min_max[1]))

    def generate_trigger_cell(self, min_max):
        assert 0 <= min_max[0] <= 1024, 'min trigger cell has to be in [0, 1024], not "{min}"'.format(min=min_max[0])
        assert 0 <= min_max[1] <= 1024, 'max trigger cell has to be in [0, 1024], not "{max}"'.format(max=min_max[1])
        self.EasyCutStrings['TriggerCell'] = 'Trigger Cell in {0}'.format(min_max)
        return TCut('trigger_cell < {max} && trigger_cell >= {min}'.format(min=min_max[0], max=min_max[1]))

    def generate_old_bucket(self):
        # only generate the cut if the region e2 exists! todo: find a smarter solution for that!
        try:
            sig2 = self.Analysis.get_signal_name('e', 2)
            string = '{sig2}=={sig1}'.format(sig2=sig2, sig1=self.Analysis.SignalName)
            return TCut(string)
        except ValueError as err:
            print err
            return TCut('')

    def generate_bucket(self, threshold=None):
        # TODO: bucket cut for high irradiation (low signals)
        sig = self.Analysis.SignalName
        threshold = self.calc_signal_threshold(show=False) if threshold is None else threshold
        string = '!(!({old_buck}) && ({sig} < {thres}))'.format(sig=sig, thres=threshold, old_buck=self.CutStrings['old_bucket'])
        # string = self.CutStrings['old_bucket'] if threshold == -30 else string
        cut = TCut(string) if self.CutStrings['old_bucket'].GetTitle() else TCut('')
        return cut

    def generate_timing(self, n_sigma=3):
        t_correction, fit = self.calc_timing_range()
        if fit is None:
            return TCut('')
        # corrected_time = '{peak} - {t_corr}'.format(peak=self.analysis.Timing.get_peak_name(corr=True, region='e'), t_corr=t_correction)  # correction for bucket cut
        corrected_time = '{peak} - {t_corr}'.format(peak=self.Analysis.Timing.get_peak_name(corr=True), t_corr=t_correction)
        string = 'TMath::Abs({cor_t} - {mp}) / {sigma} < {n_sigma}'.format(cor_t=corrected_time, mp=fit.GetParameter(1), sigma=fit.GetParameter(2), n_sigma=n_sigma)
        return TCut(string)

    def generate_threshold(self):
        return TCut('{sig}>{thresh}'.format(sig=self.Analysis.SignalName, thresh=self.calc_threshold(show=False))) if self.CutConfig['threshold'] else TCut('')

    def generate_fiducial(self):
        xy = self.CutConfig['fiducial']
        cut = None
        if xy is not None:
            cut = TCutG('fid{}'.format(self.RunNumber), 5, array([xy[0], xy[0], xy[1], xy[1], xy[0]], 'd'), array([xy[2], xy[3], xy[3], xy[2], xy[2]], 'd'))
            nr = self.Analysis.DUTNumber - 1
            cut.SetVarX(self.get_track_var(nr, 'x'))
            cut.SetVarY(self.get_track_var(nr, 'y'))
            self.Analysis.Objects.append(cut)
            cut.SetLineWidth(3)
        return TCut(cut.GetName() if cut is not None else '')

    def find_fid_cut(self, thresh=.93, show=True):
        h = self.Analysis.draw_signal_map(show=False)
        px = h.ProjectionX()
        format_histo(px, title='Projection X of the Signal Map', y_tit='Number of Entries', y_off=1.5)
        self.Analysis.draw_histo(px, lm=.12, show=show)
        py = h.ProjectionY()
        return '"{}": [{}]'.format(self.Analysis.DUTName, ', '.join('{:0.3f}'.format(i) for i in self.find_fid_margins(px, thresh) + self.find_fid_margins(py, thresh)))

    @staticmethod
    def find_fid_margins(proj, thresh):
        thresh = proj.GetMaximum() * thresh
        xbin1, xbin2 = proj.FindFirstBinAbove(thresh), proj.FindLastBinAbove(thresh)
        f1 = interpolate_two_points(proj.GetBinCenter(xbin1), proj.GetBinContent(xbin1), proj.GetBinCenter(xbin1 - 1), proj.GetBinContent(xbin1 - 1))
        f2 = interpolate_two_points(proj.GetBinCenter(xbin2), proj.GetBinContent(xbin2), proj.GetBinCenter(xbin2 + 1), proj.GetBinContent(xbin2 + 1))
        return [f1.GetX(thresh) / 10, f2.GetX(thresh) / 10]

    def get_fid_area(self):
        conf = self.CutConfig['fiducial']
        return (conf[1] - conf[0]) * (conf[3] - conf[2])

    # special cut for analysis
    def generate_pulser_cut(self, beam_on=True):
        cut = self.CutStrings['ped_sigma'] + self.CutStrings['event_range']
        cut.SetName('Pulser{0}'.format('BeamOn' if beam_on else 'BeamOff'))
        cut += self.CutStrings['beam_interruptions'] if beam_on else '!({0})'.format(self.JumpCut)
        cut += '!({0})'.format(self.CutStrings['pulser'])
        return cut

    def get_bucket_cut(self):
        cut = self.CutStrings['fiducial'] + self.CutStrings['pulser'] + TCut('!({})'.format(self.CutStrings['old_bucket']))
        cut.SetName('Bucket')
        return cut

    def generate_channel_cutstrings(self):

        # --THRESHOLD --
        self.CutStrings['threshold'] += self.generate_threshold()

        # -- PULSER CUT --
        self.CutStrings['pulser'] += '!pulser'

        # -- SATURATED CUT --
        self.CutStrings['saturated'] += '!is_saturated[{ch}]'.format(ch=self.channel)

        # -- MEDIAN CUT --
        self.CutStrings['median'] += self.generate_median()

        # -- PEDESTAL SIGMA CUT --
        self.CutStrings['ped_sigma'] += self.generate_pedestalsigma()

        # -- FIDUCIAL --
        self.CutStrings['fiducial'] += self.generate_fiducial()

        # --PEAK POSITION TIMING--
        self.CutStrings['timing'] += self.generate_timing()

        # --BUCKET --
        self.CutStrings['old_bucket'] += self.generate_old_bucket()
        self.CutStrings['bucket'] += self.generate_bucket()

    # endregion

    # ==============================================
    # HELPER FUNCTIONS

    def calc_signal_threshold(self, use_bg=False, show=True, show_all=False):
        run = self.HighRateRun if self.HighRateRun is not None else self.RunNumber
        pickle_path = self.Analysis.make_pickle_path('Cuts', 'SignalThreshold', run, self.DUTNumber)
        show = False if show_all else show

        def func():
            t = self.Analysis.info('Calculating signal threshold for bucket cut of run {run} and {d} ...'.format(run=self.Analysis.RunNumber, d=self.DUTName), next_line=False)
            h = TH1F('h', 'Bucket Cut', 200, -50, 150)
            draw_string = '{name}>>h'.format(name=self.Analysis.SignalName)
            fid = self.CutStrings['fiducial']
            cut_string = '!({buc})&&{pul}{fid}'.format(buc=self.CutStrings['old_bucket'], pul=self.CutStrings['pulser'], fid='&&{}'.format(fid.GetTitle()) if fid.GetTitle() else '')
            self.Analysis.Tree.Draw(draw_string, cut_string, 'goff')
            format_histo(h, x_tit='Pulse Height [mV]', y_tit='Entries', y_off=1.8, stats=0, fill_color=self.Analysis.FillColor)
            entries = h.GetEntries()
            if entries < 2000:
                self.Analysis.add_to_info(t)
                return -30
            # extract fit functions
            fit = fit_bucket(h)
            if fit is None:
                self.Analysis.add_to_info(t)
                return -30
            if fit is None or any([abs(fit.GetParameter(i)) < 20 for i in [0, 3]]) or fit.GetParameter(1) < fit.GetParameter(4) or fit.GetParameter(1) > 500:
                warning('bucket cut fit failed')
                self.Analysis.draw_histo(h, show=show)
                self.Analysis.add_to_info(t)
                return -30
            sig_fit = TF1('f1', 'gaus', -50, 300)
            sig_fit.SetParameters(fit.GetParameters())
            ped_fit = TF1('f2', 'gaus(0) + gaus(3)', -50, 300)
            ped_fit.SetParameters(*[fit.GetParameter(i) for i in xrange(3, 9)])
            set_root_output(True)

            # real data distribution without pedestal fit
            signal = deepcopy(h)
            signal.Add(ped_fit, -1)

            gr1 = self.Analysis.make_tgrapherrors('gr1', '#varepsilon_{bg}', marker_size=0.2)
            gr2 = self.Analysis.make_tgrapherrors('gr2', '#varepsilon_{sig}', marker_size=0.2, color=2)
            gr3 = self.Analysis.make_tgrapherrors('gr3', 'ROC Curve', marker_size=0.2)
            gr4 = self.Analysis.make_tgrapherrors('gr4', 'Signal Error', marker_size=0.2)
            xs = arange(-30, sig_fit.GetParameter(1), .1)
            errors = {}
            for i, x in enumerate(xs):
                ped = ped_fit.Integral(-50, x) / ped_fit.Integral(-50, 500)
                sig = 1 - sig_fit.Integral(-50, x) / signal.Integral()
                err = ped_fit.Integral(-50, x) / (sqrt(sig_fit.Integral(-50, x) + ped_fit.Integral(-50, x)))
                s, bg = signal.Integral(h.FindBin(x), signal.GetNbinsX() - 1), ped_fit.Integral(x, 200)
                err1 = s / sqrt(s + bg)
                errors[err1 if not use_bg else err] = x
                gr1.SetPoint(i, x, ped)
                gr2.SetPoint(i, x, sig)
                gr3.SetPoint(i, sig, ped)
                gr4.SetPoint(i, x, err1 if not use_bg else err)
            if len(errors) == 0:
                print ValueError('errors has a length of 0')
                self.Analysis.add_to_info(t)
                return -30
            max_err = max(errors.items())[1]
            c = None
            if show_all:
                set_root_output(True)
                c = self.Analysis.make_canvas('c_all', 'Signal Threshold Overview', divide=(2, 2))
            # Bucket cut plot
            self.Analysis.draw_histo(h, '', show or show_all, lm=.135, canvas=c.cd(1) if show_all else None)
            self.Analysis.draw_y_axis(max_err, h.GetYaxis().GetXmin(), h.GetMaximum(), 'threshold  ', off=.3, line=True)
            ped_fit.SetLineStyle(2)
            ped_fit.Draw('same')
            sig_fit.SetLineColor(4)
            sig_fit.SetLineStyle(3)
            sig_fit.Draw('same')
            self.Analysis.save_plots('BucketCut', canvas=c.cd(1) if show_all else get_last_canvas(), prnt=show)

            # Efficiency plot
            format_histo(gr1, title='Efficiencies', x_tit='Threshold', y_tit='Efficiency', markersize=.2)
            l2 = self.Analysis.make_legend(.78, .3)
            tits = ['#varepsilon_{bg}', gr2.GetTitle()]
            [l2.AddEntry(p, tits[i], 'l') for i, p in enumerate([gr1, gr2])]
            self.Analysis.draw_histo(gr1, '', show_all, draw_opt='apl', leg=l2, canvas=c.cd(2) if show_all else None)
            self.Analysis.draw_histo(gr2, show=show_all, draw_opt='same', canvas=c.cd(2) if show_all else get_last_canvas())
            self.Analysis.save_plots('Efficiencies', canvas=c.cd(2) if show_all else get_last_canvas(), prnt=show)

            # ROC Curve
            format_histo(gr3, y_tit='background fraction', x_tit='excluded signal fraction', markersize=0.2, y_off=1.2)
            self.Analysis.draw_histo(gr3, '', show_all, gridx=True, gridy=True, draw_opt='apl', canvas=c.cd(3) if show_all else None)
            p = self.Analysis.make_tgrapherrors('gr', 'working point', color=2)
            p.SetPoint(0, 1 - sig_fit.Integral(-50, max_err) / signal.Integral(), ped_fit.Integral(-50, max_err) / ped_fit.Integral(-50, 200))
            sleep(.1)
            latex = self.Analysis.draw_tlatex(p.GetX()[0], p.GetY()[0] + .01, 'Working Point', color=2, size=.04)
            p.GetListOfFunctions().Add(latex)
            self.Analysis.draw_histo(p, show=show_all, canvas=c.cd(3) if show_all else get_last_canvas(), draw_opt='p')
            self.Analysis.save_plots('ROC_Curve', canvas=c.cd(3) if show_all else get_last_canvas(), prnt=show)

            # Error Function plot
            format_histo(gr4, x_tit='Threshold', y_tit='1 / error', y_off=1.4)
            self.Analysis.save_histo(gr4, 'ErrorFunction', show_all, gridx=True, draw_opt='al', canvas=c.cd(4) if show_all else None, prnt=show)

            self.Analysis.Objects.append([sig_fit, ped_fit, gr2, c])

            self.Analysis.add_to_info(t)
            return max_err

        threshold = func() if show or show_all else None
        threshold = do_pickle(pickle_path, func, threshold)
        return threshold

    def __calc_pedestal_range(self, sigma_range):
        picklepath = self.Analysis.make_pickle_path('Pedestal', 'Cut', self.RunNumber, self.channel)

        def func():
            t = self.Analysis.info('generating pedestal cut for {dia} of run {run} ...'.format(run=self.Analysis.RunNumber, dia=self.Analysis.DUTName), next_line=False)
            h1 = TH1F('h_pdc', 'Pedestal Distribution', 600, -150, 150)
            self.Analysis.Tree.Draw('{name}>>h_pdc'.format(name=self.Analysis.PedestalName), '', 'goff')
            fit_pars = fit_fwhm(h1, do_fwhm=True, draw=False)
            self.Analysis.add_to_info(t)
            return fit_pars

        fit = do_pickle(picklepath, func)
        sigma = fit.Parameter(2)
        mean_ = fit.Parameter(1)
        self.PedestalFit = fit
        return [mean_ - sigma_range * sigma, mean_ + sigma_range * sigma]

    def calc_threshold(self, show=True):
        pickle_path = self.Analysis.make_pickle_path('Cuts', 'Threshold', self.Analysis.RunNumber, self.channel)

        def func():
            self.Analysis.Tree.Draw(self.Analysis.SignalName, '', 'goff', 5000)
            xvals = sorted([self.Analysis.Tree.GetV1()[i] for i in xrange(5000)])
            x_range = [xvals[0] - 5, xvals[-5]]
            h = self.Analysis.draw_signal_distribution(show=show, cut=self.generate_fiducial(), x_range=x_range, bin_width=1)
            s = TSpectrum(3)
            s.Search(h)
            peaks = [s.GetPositionX()[i] for i in xrange(s.GetNPeaks())]
            h.GetXaxis().SetRangeUser(peaks[0], peaks[-1])
            x_start = h.GetBinCenter(h.GetMinimumBin())
            h.GetXaxis().UnZoom()
            fit = TF1('fit', 'landau', x_start, h.GetXaxis().GetXmax())
            h.Fit(fit, 'q{0}'.format(0 if not show else ''), '', x_start, h.GetXaxis().GetXmax())
            return fit.GetX(.1, 0, peaks[-1])

        threshold = func() if show else None
        return do_pickle(pickle_path, func, threshold)

    def calc_timing_range(self, redo=False):
        pickle_path = self.Analysis.make_pickle_path('Cuts', 'TimingRange', self.RunNumber, self.DUTNumber)

        def func():
            t = self.Analysis.info('generating timing cut for {dia} of run {run} ...'.format(run=self.Analysis.RunNumber, dia=self.Analysis.DUTName), next_line=False)
            cut = self.generate_special_cut(excluded=['timing'], prnt=False, name='timing_cut')
            t_correction = self.Analysis.Timing.calc_fine_correction(redo=redo)
            h = self.Analysis.Timing.draw_peaks(show=False, cut=cut, fine_corr=t_correction != '0', prnt=False, redo=redo)
            fit = h.GetListOfFunctions()[1]
            if fit.GetParameter(2) > 15:  # fit failed
                fit.SetParameter(1, h.GetBinCenter(h.GetMinimumBin()))
                fit.SetParameter(2, 15)
            self.Analysis.add_to_info(t)
            self.Analysis.info('Peak Timing: Mean: {0}, sigma: {1}'.format(fit.GetParameter(1), fit.GetParameter(2)))
            return t_correction, fit

        return do_pickle(pickle_path, func, redo=redo)
