from numpy import zeros, array
from ROOT import TH2F, TCanvas, gStyle

__author__ = 'micha'


# ==============================================
# MAIN CLASS
# ==============================================
class Extrema2D:

    def __init__(self, signal_histo, mean_histo):
        self.SignalHisto = signal_histo
        self.MeanHisto = mean_histo
        self.Thresholds = self.find_thresholds()
        # attributes
        self.rows = self.SignalHisto.GetNbinsY() + 2
        self.cols = self.SignalHisto.GetNbinsX() + 2
        # new histograms
        self.VotingHistos = self.create_voting_histo()
        self.canvas = None

    def find_thresholds(self):
        dic = {}
        xq = array([i / 100. for i in xrange(5, 100, 10)])
        nq = len(xq)
        thresh = zeros(nq)
        self.MeanHisto.GetQuantiles(nq, thresh, xq)
        dic['min'] = thresh[:(nq / 2)]
        dic['max'] = thresh[(-nq / 2):]
        return dic

    def horizontal_scan(self):
        for row in xrange(self.rows):
            for col in xrange(self.cols):
                self.__add_local_extrema(col, row, mode='horizontal')

    def vertical_scan(self):
        for col in xrange(self.cols):
            for row in xrange(self.rows):
                self.__add_local_extrema(col, row, mode='vertical')

    def sw_ne_scan(self):
        rows = [row for row in xrange(self.rows - 2, 0, -1)]
        cols = [0] * (self.rows - 2)
        rows += [0] * (self.cols - 1)
        cols += [col for col in xrange(self.cols - 1)]
        for row, col in zip(rows, cols):
            while row < self.rows and col < self.cols:
                self.__add_local_extrema(col, row, mode='swne')
                row += 1
                col += 1

    def nw_se_scan(self):
        rows = [row for row in xrange(1, self.rows - 1)]
        cols = [0] * (self.rows - 2)
        print len(rows), len(cols)
        rows += [self.rows - 1] * (self.cols - 1)
        cols += [col for col in xrange(self.cols - 1)]
        print len(rows), len(cols)
        for row, col in zip(rows, cols):
            while row >= 0 and col < self.cols:
                print col, row,
                self.__add_local_extrema(col, row, mode='nwse')
                row -= 1
                col += 1
            print

    def make_all_line_scans(self):
        self.horizontal_scan()
        self.vertical_scan()
        # self.sw_ne_scan()
        # self.nw_se_scan()
        self.show_voting_histos()

    def region_scan(self):
        for col in xrange(self.cols):
            for row in xrange(self.rows):
                for threshold in self.Thresholds['max']:
                    if self.SignalHisto.GetBinContent(col, row) > threshold:
                        old_content = self.VotingHistos['max'].GetBinContent(col, row)
                        self.VotingHistos['max'].SetBinContent(col, row, old_content + 1)
                for threshold in self.Thresholds['min']:
                    if self.SignalHisto.GetBinContent(col, row) < threshold:
                        old_content = self.VotingHistos['min'].GetBinContent(col, row)
                        self.VotingHistos['min'].SetBinContent(col, row, old_content + 1)

    def square_scan(self, size=1):
        rows = [i for i in xrange(-size, size + 1)] * (2 * size + 1)
        cols = sorted(rows)
        for col in xrange(1, self.cols - 1):
            for row in xrange(1, self.rows - 1):
                square = [self.SignalHisto.GetBinContent(col + x, row + y) for x, y in zip(cols, rows)]
                if max(square) == self.SignalHisto.GetBinContent(col, row) and max(square) > self.Thresholds['max'][0]:
                    self.VotingHistos['max'].SetBinContent(col, row, 1)
                elif min(square) == self.SignalHisto.GetBinContent(col, row) and min(square) < self.Thresholds['min'][-1]:
                    self.VotingHistos['min'].SetBinContent(col, row, 1)

    def __add_local_extrema(self, col, row, mode):
        if mode == 'horizontal':
            cols, rows = [col - 1, col, col + 1], [row] * 3
        elif mode == 'vertical':
            cols, rows = [col] * 3, [row - 1, row, row + 1]
        elif mode == 'swne':
            cols, rows = [col - 1, col, col + 1], [row - 1, row, row + 1]
        else:
            cols, rows = [col - 1, col, col + 1], [row + 1, row, row - 1]

        start = self.SignalHisto.GetBinContent(cols[0], rows[0])
        center = self.SignalHisto.GetBinContent(cols[1], rows[1])
        end = self.SignalHisto.GetBinContent(cols[2], rows[2])
        print start, center, end
        if start <= center >= end and center > self.Thresholds['max'][0]:
            old_content = self.VotingHistos['max'].GetBinContent(col, row)
            self.VotingHistos['max'].SetBinContent(col, row, old_content + 1)
        elif start >= center <= end and center < self.Thresholds['min'][-1]:
            old_content = self.VotingHistos['min'].GetBinContent(col, row)
            self.VotingHistos['min'].SetBinContent(col, row, old_content + 1)

    def create_voting_histo(self):
        axes = [self.SignalHisto.GetXaxis(), self.SignalHisto.GetYaxis()]
        x = [self.SignalHisto.GetNbinsX(), axes[0].GetXmin(), axes[0].GetXmax()]
        y = [self.SignalHisto.GetNbinsY(), axes[1].GetXmin(), axes[1].GetXmax()]
        names = ['min', 'max']
        return {name: TH2F('voting_{}'.format(name), 'Voting Histogram', x[0], x[1], x[2], y[0], y[1], y[2]) for name in names}

    def show_voting_histos(self):
        gStyle.SetPalette(51)
        c = TCanvas('c', 'Voting Histos', 1600, 800)
        c.Divide(2, 1)
        for i, histo in enumerate(self.VotingHistos.itervalues(), 1):
            c.cd(i)
            histo.Draw('colz')
        self.canvas = c

    def clear_voting_histos(self):
        for histo in self.VotingHistos.itervalues():
            histo.Reset()
