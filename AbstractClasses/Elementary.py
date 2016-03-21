import os
import pickle
import re
import sys
from copy import deepcopy
from glob import glob
from shutil import copyfile
from time import time
from datetime import datetime

import ROOT
from ROOT import gROOT, TGraphErrors, TGaxis, TLatex, TGraphAsymmErrors, TSpectrum, TF1, TMath


class Elementary(object):
    """
    The Elementary class provides default behaviour objects in the analysis framework and is the Mother of all myPadAnalysis objects.
    It provides, among other things, a verbose printing method or a save plot method containing a global save directory handling.
    """

    default_testcampaign = '201510'
    TESTCAMPAIGN = None

    def __init__(self, verbose=False):
        self.verbose = verbose
        self.save_directory = self.get_program_dir() + 'Results/'

        self.set_test_campaign(self.default_testcampaign)

        self.load_config()
        self.aimedFluxes = [3, 20, 60, 600, 2000, 5000]
        # colors
        self.count = 0
        self.colors = self.create_colorlist()
        # self.channel = None

    def load_config(self):
        pass

    @staticmethod
    def create_colorlist():
        col_names = [ROOT.kGreen, ROOT.kOrange, ROOT.kViolet, ROOT.kYellow, ROOT.kRed, ROOT.kBlue, ROOT.kMagenta, ROOT.kAzure, ROOT.kCyan, ROOT.kTeal]
        colors = []
        for color in col_names:
            colors.append(color + 1)
        for color in col_names:
            colors.append(color + 3)
        return colors

    def get_color(self):
        self.count %= 20
        color = self.colors[self.count]
        self.count += 1
        return color

    def reset_colors(self):
        self.count = 0

    def verbose_print(self, *args):
        """
        Print command if verbose is activated.
        :param args:
        """
        if self.verbose:
            # Print each argument separately so caller doesn't need to put everything to be printed into a single string.
            for arg in args:
                print arg,
            print

    @staticmethod
    def has_bit(num, bit):
        assert (num >= 0 and type(num) is int), 'num has to be non negative int'
        return bool(num & 1 << bit)

    def set_save_directory(self, directory="Results/"):
        if not directory[-1] == "/":
            directory += "/"
        self.save_directory = directory

    def save_plots(self, savename, file_type=None, save_dir=None, sub_dir=None, canvas=None, ind=0, ch='dia'):
        """
        Saves the canvas at the desired location. If no canvas is passed as argument, the active canvas will be saved. However for applications without graphical interface,
        such as in SSl terminals, it is recommended to pass the canvas to the method.
        :param savename:
        :param file_type:
        :param save_dir:
        :param sub_dir:
        :param canvas:
        :param ind: index of the collection
        :param ch: if None print both dias (dirty fix)
        """
        save_dir = self.save_directory if save_dir is None else save_dir
        file_type = '.png' if file_type is None else '.{end}'.format(end=file_type)
        sub_dir = '' if sub_dir is None else '{subdir}/'.format(subdir=sub_dir)
        resultsdir = save_dir + sub_dir
        if not os.path.exists(resultsdir):
            os.makedirs(resultsdir)
        if canvas is None:
            try:
                c = gROOT.GetListOfCanvases()
                # pad = gROOT.GetSelectedPad()
                canvas = c[-1]
            except Exception as inst:
                print '\n\n{delim}\nERROR in get canvas!\n{msg}\n{delim}\n\n'.format(delim=len(str(inst)) * '-', msg=inst)
                return
        channel = self.channel if hasattr(self, 'channel') else None
        if hasattr(self, 'run'):
            self.run.draw_run_info(channel=ch if ch is None else channel, canvas=canvas)
        elif hasattr(self, 'analysis'):
            print 'has analysis'
            self.analysis.run.draw_run_info(channel=ch if ch is None else channel, canvas=canvas)
        elif hasattr(self, 'collection'):
            runs = [self.collection.keys()[0], self.collection.keys()[-1], self.collection.values()[0].run.get_rate_string(), self.collection.values()[-1].run.get_rate_string()]
            if not ind:
                self.collection.values()[ind].run.draw_run_info(channel=ch if ch is None else self.collection.values()[ind].channel, canvas=canvas, runs=runs)
            else:
                self.collection.values()[ind].run.draw_run_info(channel=ch if ch is None else self.collection.values()[ind].channel, canvas=canvas)
        canvas.Update()
        try:
            canvas.SaveAs(resultsdir + savename + file_type)
        except Exception as inst:
            print '\n\n{delim}\nERROR in save plots!\n{msg}\n{delim}\n\n'.format(delim=len(str(inst)) * '-', msg=inst)

    def create_new_testcampaign(self):
        year = raw_input('Enter the year of the test campgaign (YYYY): ')
        month = raw_input('Enter the month of the testcampaign: ').zfill(2)
        if year + month in self.find_test_campaigns():
            print 'This test campaign already exists! --> returning'
            return
        new_tc = year + month
        new_tc_cfg = year + month + '.cfg'
        conf_dir = self.get_program_dir() + 'Configuration/'
        names = []
        old_tc_cfg = ''
        for f in glob(conf_dir + '*'):
            name = f.split('/')[-1].split('_')
            if len(name) > 1 and name[1].startswith('20') and name[0] not in names:
                if name[1] > old_tc_cfg:
                    old_tc_cfg = name[1]
                names.append(name[0])
        old_tc = old_tc_cfg.split('.')[0]
        for name in names:
            file_name = conf_dir + name + '_'
            copyfile(file_name + old_tc_cfg, file_name + new_tc_cfg)
            f = open(file_name + new_tc_cfg, 'r+')
            lines = []
            for line in f.readlines():
                print line
                print old_tc[2:], new_tc[2:], old_tc[:4] + '_' + old_tc[4:], year + '_' + month
                line = line.replace(old_tc[2:], new_tc[2:])
                old = old_tc[:4] + '_' + old_tc[4:]
                lines.append(line.replace(old, year + '_' + month))
            f.seek(0)
            f.writelines(lines)
            f.close()

    @classmethod
    def set_test_campaign(cls, campaign='201508'):
        campaigns = cls.find_test_campaigns()
        if not str(campaign) in campaigns:
            print 'This Testcampaign does not exist yet! Use create_new_testcampaign!\nExisting campaigns: {camp}'.format(camp=campaigns)
            return
        if Elementary.TESTCAMPAIGN is None:
            Elementary.TESTCAMPAIGN = str(campaign)

    def print_testcampaign(self):
        tc = datetime.strptime(self.TESTCAMPAIGN, '%Y%m')
        print 'TESTCAMPAIGN:', tc.strftime('%b %Y')

    @classmethod
    def find_test_campaigns(cls):
        conf_dir = cls.get_program_dir() + 'Configuration/'
        names = glob(conf_dir + 'RunConfig_*')
        campaigns = [re.split('_|\.', name)[1] for name in names]
        campaigns = [camp for i, camp in enumerate(campaigns) if camp not in campaigns[i + 1:]]
        return sorted(campaigns)

    @staticmethod
    def print_elapsed_time(start, what='This'):
        string = '{1} took {0:2.2f} seconds'.format(time() - start, what)
        print string
        return string

    @staticmethod
    def do_pickle(path, function, value=0):
        if value:
            f = open(path, 'w')
            pickle.dump(value, f)
            f.close()
            return value
        try:
            f = open(path, 'r')
            ret_val = pickle.load(f)
            f.close()
        except IOError:
            ret_val = function()
            f = open(path, 'w')
            pickle.dump(ret_val, f)
            f.close()
        return ret_val

    @staticmethod
    def set_root_output(status=True):
        if status:
            gROOT.SetBatch(0)
            gROOT.ProcessLine("gErrorIgnoreLevel = 0;")
        else:
            gROOT.SetBatch(1)
            gROOT.ProcessLine("gErrorIgnoreLevel = kError;")

    @staticmethod
    def make_tgrapherrors(name, title, color=1, marker=20, marker_size=1, width=1, asym_err=False):
        gr = TGraphErrors() if not asym_err else TGraphAsymmErrors()
        gr.SetTitle(title)
        gr.SetName(name)
        gr.SetMarkerStyle(marker)
        gr.SetMarkerColor(color)
        gr.SetLineColor(color)
        gr.SetMarkerSize(marker_size)
        gr.SetLineWidth(width)
        return gr

    @staticmethod
    def make_tgaxis(x, y1, y2, title, color=1, width=1, offset=.15, tit_size=.04, line=True, opt='+SU'):
        a = TGaxis(x, y1, x, y2, y1, y2, 510, opt)
        a.SetLineColor(color)
        if line:
            a.SetTickSize(0)
            a.SetLabelSize(0)
        a.SetTitleSize(tit_size)
        a.SetTitleOffset(offset)
        a.SetTitle(title + '  ')
        a.SetTitleColor(color)
        a.SetLineWidth(width)
        return a

    @staticmethod
    def format_histo(histo, name='', title='', x_tit='', y_tit='', marker=20, color=1, markersize=1, x_off=1, y_off=1, lw=1):
        h = histo
        h.SetTitle(title) if title else h.SetTitle(h.GetTitle())
        h.SetName(name) if name else h.SetName(h.GetName())
        h.SetMarkerStyle(marker)
        h.SetMarkerColor(color) if color is not None else h.SetMarkerColor(h.GetMarkerColor())
        h.SetLineColor(color) if color is not None else h.SetLineColor(h.GetLineColor())
        h.SetMarkerSize(markersize)
        h.GetXaxis().SetTitle(x_tit) if x_tit else h.GetXaxis().GetTitle()
        h.GetXaxis().SetTitleOffset(x_off)
        h.GetYaxis().SetTitle(y_tit) if y_tit else h.GetYaxis().GetTitle()
        h.GetYaxis().SetTitleOffset(y_off)
        h.SetLineWidth(lw)

    @staticmethod
    def make_tlatex(x, y, text, align=20, color=1, size=.05):
        l = TLatex(x, y, text)
        l.SetTextAlign(align)
        l.SetTextColor(color)
        l.SetTextSize(size)
        return l

    @staticmethod
    def calc_fwhm(histo):
        h = histo
        max_ = h.GetMaximum()
        bin1 = h.FindFirstBinAbove(max_ / 2)
        bin2 = h.FindLastBinAbove(max_ / 2)
        fwhm = h.GetBinCenter(bin2) - h.GetBinCenter(bin1)
        return fwhm

    @staticmethod
    def get_program_dir():
        arg = 2 if len(sys.argv) > 2 and len(sys.argv[2]) > 4 else 0
        path = os.path.dirname(os.path.realpath(sys.argv[arg])).split('/')
        ret_val = ''
        for i in range(len(path) - 1):
            ret_val += path[i] + '/'
        return ret_val

    @staticmethod
    def adj_length(value):
        string = str(value)
        num = len(string) / 4 * 4 + 4
        return string.ljust(num)

    @staticmethod
    def fit_fwhm(histo, fitfunc='gaus', do_fwhm=True, draw=False):
        h = histo
        if do_fwhm:
            peak_pos = h.GetBinCenter(h.GetMaximumBin())
            bin1 = h.FindFirstBinAbove(h.GetMaximum() / 2)
            bin2 = h.FindLastBinAbove(h.GetMaximum() / 2)
            fwhm = h.GetBinCenter(bin2) - h.GetBinCenter(bin1)
            option = 'qs' if draw else 'qs0'
            fit = h.Fit(fitfunc, option, '', peak_pos - fwhm / 2, peak_pos + fwhm / 2)
        else:
            fit = h.Fit(fitfunc, 'qs')
        return fit

    @staticmethod
    def del_rootobj(obj):
        if obj is None:
            return
        if obj.IsA().GetName() != 'TCanvas':
            obj.Delete()

    @staticmethod
    def normalise_histo(histo):
        h = histo
        h.Scale(1 / h.Integral(1, h.GetNbinsX()))
        return h

    @staticmethod
    def do_nothing():
        pass

    @staticmethod
    def triple_gauss_fit(histo, show=True):
        gROOT.ProcessLine('gErrorIgnoreLevel = kError;')
        h = histo
        fit = TF1('fit', 'gaus(0) + gaus(3) + gaus(6)')
        s = TSpectrum(2)
        s.Search(h)
        fit.SetParLimits(0, .8 * s.GetPositionY()[1], 1.2 * s.GetPositionY()[1])
        fit.SetParLimits(1, s.GetPositionX()[1] - 10, s.GetPositionX()[1] + 10)
        fit.SetParLimits(2, 5, 50)
        fit.SetParLimits(3, .8 * s.GetPositionY()[0], 1.2 * s.GetPositionY()[0])
        fit.SetParLimits(4, s.GetPositionX()[0] - 5, s.GetPositionX()[0] + 5)
        fit.SetParLimits(5, 1, 10)
        fit.SetParLimits(6, 10, s.GetPositionY()[1])
        fit.SetParLimits(7, s.GetPositionX()[0], s.GetPositionX()[1])
        fit.SetParLimits(8, 1, 10)
        for i in xrange(5):
            h.Fit(fit, 'qs{0}'.format('' if show else '0'), '', -50, s.GetPositionX()[1])
        gROOT.ProcessLine('gErrorIgnoreLevel = 0;')
        return fit

    @staticmethod
    def make_class_from_instance(instance):
        copy = deepcopy(instance.__dict__)
        instance_factory = type('instance_factory', (instance.__class__, ), {})
        instance_factory.__init__ = lambda self, *args, **kwargs: self.__dict__.update(copy)
        return instance_factory

    @staticmethod
    def isfloat(string):
        try:
            float(string)
            return True
        except ValueError:
            return False

    @staticmethod
    def find_graph_margins(graphs):
        extrema = [max([TMath.MaxElement(gr.GetN(), gr.GetY()) for gr in graphs]), min([TMath.MinElement(gr.GetN(), gr.GetY()) for gr in graphs])]
        return [extrema[1] - (extrema[0] - extrema[1]) * .1, extrema[0] + (extrema[0] - extrema[1]) * .1]

    @staticmethod
    def print_banner(msg, symbol='='):
        print '\n{delim}\n{msg}\n{delim}\n'.format(delim=len(str(msg)) * symbol, msg=msg)

if __name__ == "__main__":
    z = Elementary()
