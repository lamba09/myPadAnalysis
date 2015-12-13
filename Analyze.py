import numpy as np
import ROOT
import sys # to get arguments
import os # for folder and file handling
from AbstractClasses.AnalysisClass import Analysis
from AbstractClasses.AnalysisCollection import AnalysisCollection
from AbstractClasses.RunClass import Run
from AbstractClasses.MCRun import MCRun
from Runinfos.RunInfo import RunInfo
from array import array
from AbstractClasses.ConfigClass import *
from AbstractClasses.MCPerformance import MCPerformance
#from Configuration.initialize_ROOT import initialize_ROOT


if __name__ == "__main__":
    #initialize_ROOT()
    # get run numbers to analyze from arguments (type: list):
    run_numbers = map(int, [i for i in sys.argv if i.isdigit() == True])

    # config
    show_plots = True
    minimum_statistics = 100 # don't draw bins which contain less than minimum_statistics hits
    binsize = 100
    min_percent = 0.001
    max_percent = 100
    number_of_hits = 300000 # change in MonteCarloConfig.cfg !
    amplitude = 0. # change in MonteCarloConfig.cfg !
    savepath = "Results/Analyze/"

    if 'v' in sys.argv or '-v' in sys.argv or 'V' in sys.argv:
        verbose = True
    else:
        verbose = False

    if '-mc' in sys.argv or 'mc' in sys.argv or 'MC' in sys.argv:
        run = MCRun(validate=False,verbose=verbose)
    else:
        run = Run(validate=False,verbose=verbose)

    run.SetSaveDirectory(savepath)

    MaxNrOfRuns = 9999
    if(len(run_numbers) == 0):
        MaxNrOfRuns = int(raw_input("No runs specified. Set Maximal number of runs to analyze (0-999) press Enter to select all Runs: "))
        if MaxNrOfRuns == '':
            MaxNrOfRuns = 9999
            print "All runs selected..."
        assert (0 <= MaxNrOfRuns < 10000), "Invalid maximal run quantity"
        all_run_numbers =  RunInfo.runs.keys()
        run_numbers = []
        for i in all_run_numbers:
            run.set_run(i)
            if run.current_run['data_type'] == 0: # 0 = data, 1 = pedestrial, 2 = voltagescan, 3 =  long run, 4 = other
                run_numbers += [i]
        run_numbers = run_numbers[:MaxNrOfRuns]
    print "Starting analysis with ",len(run_numbers)," runs:"
    run.validate_runs(run_numbers)
    print run_numbers


    collection = AnalysisCollection()
    for run_number in run_numbers:

        if run.set_run(run_number): # run must exist and is set

            if True or run.diamond.Specifications['Irradiation'] == 'no':
                print run_number

                #
                newAnalysis = Analysis(run,Config(binsize))
                newAnalysis.DoAnalysis(minimum_statistics)
                # newAnalysis.CreatePlots(True,'2D_Signal_dist',show3d=True)
                # # # # newAnalysis.CreateMeanSignalHistogram(True)
                newAnalysis.CreateBoth(saveplots=True)
                # newAnalysis.Pad.CreateSignalHistogram(saveplot=True)
                # #
                # # #print newAnalysis.Pad.ListOfBins[newAnalysis.Pad.GetBinNumber(0.05,0.05)].GetEntries()
                # # newAnalysis.Pad.ShowBinXYSignalHisto(0.08,0.3,True)
                # # newAnalysis.Pad.ShowBinXYSignalHisto(-0.04,0.3,True)
                # #
                # # newAnalysis.Pad.UnselectAllBins()
                # # bin1 = newAnalysis.Pad.GetBinByCoordinates(-0.04,0.3)
                # # newAnalysis.Pad.SelectSignalStrengthRegion(bin1,0.1,True,-0.09,0.02,0.22,0.36)
                # #
                # # #newAnalysis.Pad.ShowSelectedBins()
                # # newAnalysis.Pad.ShowCombinedKDistribution(True,'combinedK_1')
                # #
                # # newAnalysis.Pad.UnselectAllBins()
                # # bin2 = newAnalysis.Pad.GetBinByCoordinates(0.0835,0.3)
                # # newAnalysis.Pad.SelectSignalStrengthRegion(bin2,0.1,True,0.01,0.14,0.23,0.36)
                # #
                # # newAnalysis.Pad.ShowCombinedKDistribution(True,'combinedK_2')
                # #
                # # newAnalysis.Pad.UnselectAllBins()
                # # newAnalysis.Pad.SelectSignalStrengthRegion(bin1,0.1,True,-0.09,0.02,0.22,0.36)
                # # newAnalysis.Pad.SelectSignalStrengthRegion(bin2,0.1,True,0.01,0.14,0.23,0.36)
                # # newAnalysis.Pad.ShowCombinedKDistribution(True,'combinedK_both')
                #
                # newAnalysis.Pad.UnselectAllBins()
                #
                # bin3 = newAnalysis.Pad.GetBinByNumber(newAnalysis.Pad.GetMaximumSignalResponseBinNumber())
                # print bin3.GetBinCoordinates()
                # # print bin3.GetBinCenter()
                # newAnalysis.Pad.GetSignalInRow(height=0.33, show=True)
                # newAnalysis.Pad.GetSignalInRow(height=0.17, show=True)
                #
                # newAnalysis.Pad.GetSignalInColumn(position=0.13, show=True)
                # newAnalysis.Pad.ShowBinXYSignalHisto(-0.03,0.19, saveplot=True, show_fit=True)
                # newAnalysis.Pad.ShowBinXYSignalHisto(0.13,0.03,True)
                newAnalysis.FindMaxima(show=True, binning=binsize, minimum_bincontent=minimum_statistics)
                newAnalysis.FindMinima(show=True, binning=binsize, minimum_bincontent=minimum_statistics)
                # newAnalysis.MaximaAnalysis.Pad.ShowBinXYSignalHisto(-0.04,0.3,saveplot=True, show_fit=True)
                # newAnalysis.MaximaAnalysis.Pad.ShowBinXYSignalHisto(0.07,0.3,saveplot=True, show_fit=True)
                # newAnalysis.MaximaAnalysis.Pad.ShowBinXYSignalHisto(0.12,0.33, saveplot=True, show_fit=True)
                #newAnalysis.MaximaAnalysis.Pad.GetSignalInRow(0.3,True)
                # newAnalysis.MaximaAnalysis.Pad.GetSignalInRow(0.15,True)
                # newAnalysis.MaximaAnalysis.Pad.GetSignalInColumn(0.06,True)
                # newAnalysis.MaximaAnalysis.Pad.GetSignalInRow(0.35,True)
                # newAnalysis.MaximaAnalysis.GetMPVSigmas(show = True)
                #

                newAnalysis.combined_canvas.cd(1)
                if run.IsMonteCarlo:
                    print "Run is MONTE CARLO"
                    if run.SignalParameters[0] > 0:
                        height = run.SignalParameters[4]
                        newAnalysis.ExtremeAnalysis.Pad.GetSignalInRow(height, show=True)
                    newAnalysis.combined_canvas.cd(1)
                    newAnalysis.ExtremeAnalysis.Pad.MaximaSearch.real_peaks.SetMarkerColor(ROOT.kBlue)
                    newAnalysis.ExtremeAnalysis.Pad.MaximaSearch.real_peaks.SetLineColor(ROOT.kBlue)
                    newAnalysis.ExtremeAnalysis.Pad.MaximaSearch.real_peaks.Draw('SAME P0')
                # newAnalysis.ExtremeAnalysis.Pad.MaximaSearch.found_extrema.SetMarkerColor(ROOT.kGreen+2)
                # newAnalysis.ExtremeAnalysis.Pad.MaximaSearch.found_extrema.Draw('SAME P0')
                minima = newAnalysis.ExtremeAnalysis.ExtremaResults['FoundMinima']
                for i in xrange(len(minima)):
                    text = ROOT.TText()
                    text.SetTextColor(ROOT.kBlue-4)
                    text.DrawText(minima[i][0]-0.01, minima[i][1]-0.005, 'low')
                maxima = newAnalysis.ExtremeAnalysis.ExtremaResults['FoundMaxima']
                for i in xrange(len(maxima)):
                    text = ROOT.TText()
                    text.SetTextColor(ROOT.kRed)
                    text.DrawText(maxima[i][0]-0.02, maxima[i][1]-0.005, 'high')
                if len(maxima)*len(minima)>0:
                    maxbin = newAnalysis.ExtremeAnalysis.Pad.GetBinByCoordinates(*(maxima[0]))
                    maxbin.FitLandau()
                    minbin = newAnalysis.ExtremeAnalysis.Pad.GetBinByCoordinates(*(minima[0]))
                    minbin.FitLandau()
                    print '\nApproximated Signal Amplitude: {0:0.0f}% - (high/low approximation)\n'.format(100.*(maxbin.Fit['MPV']/minbin.Fit['MPV']-1.))


                q = array('d', [1.*min_percent/100., 1.*max_percent/100.])
                y = array('d', [0,0])
                newAnalysis.ExtremeAnalysis.MeanSignalHisto.GetQuantiles(2, y, q)
                print '\n\n\nApproximated Signal Amplitude: {0:0.0f}% - ({1:0.0f}%/{2:0.0f}% Quantiles approximation)\n\n\n'.format(100.*(y[1]/y[0]-1.), max_percent, min_percent)
                # newAnalysis.ExtremeAnalysis.Pad.MinimaSearch.found_extrema.SetMarkerColor(ROOT.kBlue-4)
                # newAnalysis.ExtremeAnalysis.Pad.MinimaSearch.found_extrema.Draw('SAME P0')
                ROOT.gStyle.SetPalette(53)
                ROOT.gStyle.SetNumberContours(999)
                newAnalysis.combined_canvas.Update()
                ROOT.gPad.Print(savepath+"Combined_Plot.png")


                #
                # # newAnalysis.Pad.SelectSignalStrengthRegion(bin3, sensitivity=0.14, activate=True)
                # # newAnalysis.Pad.ShowSelectedBins()
                # # newAnalysis.Pad.ShowCombinedKDistribution(saveplots=True, savename='combinedK_all')
                # #
                newAnalysis.CreateHitsDistribution(saveplot=True, drawoption='colz', RemoveLowStatBins=minimum_statistics)
                # newAnalysis.ExportMC()


                newAnalysis.GetSignalHeight()

                newAnalysis.ShowTotalSignalHistogram(save=True)

                newAnalysis.SignalTimeEvolution(time_spacing=5)

                newAnalysis.RateTimeEvolution(show = True, time_spacing=3)

                newAnalysis.RateTimeEvolution(show = True, time_spacing=5, binnumber=newAnalysis.Pad.GetBinNumber(-0.075,0.215))
                newAnalysis.RateTimeEvolution(show = True, time_spacing=5, binnumber=newAnalysis.Pad.GetBinNumber(0.025,0.145))


                collection.AddAnalysis(newAnalysis)



        else:
            print "Analysis of run ",run_number, " failed"


    # collection.CreateFWHMPlot()
    # collection.CreateSigmaMPVPlot()

    # MCAnalysis = MCPerformance()
    # MCAnalysis.DoSignalHeightScan()

    collection.SignalHeightScan()
    collection.PeakComparison()



    if show_plots: raw_input("Press ENTER to quit:")

    # ROOT.gDirectory.GetList().ls()
    # ROOT.gROOT.GetListOfFiles().ls()


