import ROOT
from AbstractClasses.Elementary import Elementary
from ROOT import gROOT
import types as t


class PreAnalysisPlot(Elementary):
    '''
    Produces 3 plots inside one canvas:
     - mean signal vs time distribution
     - 2d signal vs time distribution
     - pedestal vs time distribution

    Cuts:
     - cuts from config file "AnalysisConfig.cfg"
     - first XXX events excluded (defined in same cfg file)

     to remove also beam interruption events, call the function
     Analysis.RemoveBeamInterruptions() first
    '''
    
    def __init__(self, analysis, channel, canvas=None, binning=5000):
        Elementary.__init__(self)
        self.analysis = analysis
        if canvas == None:
            canvas = ROOT.TCanvas("signalTimeCanvasRun"+str(self.analysis.run.run_number)+"Ch"+str(channel), "signalTimeCanvas"+"Ch"+str(channel), 650, 700)
        self.signalTimeCanvas = canvas
        self.channel = channel
        self.binning = binning
        self.padymargins = {}
        
    def Draw(self, mode="mean", savePlot=True, setyscale_sig=None, setyscale_ped=None):
        assert(mode in ["mean", "Mean", "fit", "Fit"])
        assert(setyscale_sig==None or type(setyscale_sig) is t.ListType)


        drawOption2D = "COLZ"
        if not hasattr(self, "pedgraph"):
            nbins = int(self.analysis.GetEventAtTime(9999999))/int(self.binning)

            #define graphs:
            self.graph = ROOT.TGraphErrors()
            graphtitle = 'Run{runnumber}: {diamond} Signal Time Evolution'.format(runnumber=self.analysis.run.run_number, diamond=self.analysis.run.diamondname[self.channel])
            self.graph.SetNameTitle('graph', graphtitle)
            self.pedgraph = ROOT.TGraphErrors()
            pedgraphtitle = 'Run{runnumber}: {diamond} Pedestal Time Evolution'.format(runnumber=self.analysis.run.run_number, diamond=self.analysis.run.diamondname[self.channel])
            self.pedgraph.SetNameTitle('ped_graph', pedgraphtitle)

            #set Canvas
            if not bool(self.signalTimeCanvas):
                self.signalTimeCanvas = ROOT.TCanvas("signalTimeCanvas"+"Ch"+str(self.channel), "signalTimeCanvas"+"Ch"+str(self.channel), 650, 700)
            self.signalTimeCanvas.Divide(1,3)
            self.signalTimeCanvas.cd(1)

            #fill graph
            self.analysis.run.tree.GetEvent(0)
            startevent = self.analysis.run.tree.event_number
            starttime = self.analysis.run.tree.time
            self.analysis.run.tree.GetEvent(self.analysis.run.tree.GetEntries()-1)
            endevent = self.analysis.run.tree.event_number
            endtime = self.analysis.run.tree.time
            totalMinutes = (endtime-starttime)/60000.
            print "Total Minutes: {tot} nbins={nbins}".format(tot=totalMinutes, nbins=nbins)
            signaltime = ROOT.TH2D("signaltime" ,"signaltime", nbins, 0, (endtime-starttime), 200, -100, 500)
            pedestaltime = ROOT.TH2D("pedestaltime" ,"pedestaltime", nbins, 0, (endtime-starttime), 200, -100, 500)
            print "making PreAnalysis using\nSignal def:\n\t{signal}\nCut:\n\t{cut}".format(signal=self.analysis.signaldefinition[self.channel], cut=self.analysis.GetCut(self.channel))
            test = self.analysis.run.tree.Draw((self.analysis.signaldefinition[self.channel]+":(time-{starttime})>>signaltime").format(channel=self.channel, starttime=starttime), self.analysis.GetCut(self.channel), drawOption2D, self.analysis.GetNEventsCut(channel=self.channel), self.analysis.GetMinEventCut(channel=self.channel))
            self.analysis.run.tree.Draw(self.analysis.pedestalname+"[{channel}]:(time-{starttime})>>pedestaltime".format(channel=self.channel, starttime=starttime), self.analysis.GetCut(self.channel), drawOption2D, self.analysis.GetNEventsCut(channel=self.channel), self.analysis.GetMinEventCut(channel=self.channel))

            print "starttime: ", starttime
            print "startevent:", startevent
            print "endtime:", endtime
            print "endevent:", endevent

            assert(int(test)>0), "Error: No signal event with current settings.. \nThe Cut is:\n\t"+self.analysis.GetCut(self.channel)

            count = 0
            final_i = 0
            runnumber = self.analysis.run.run_number
            self.signalProjection = {}
            for i in xrange(nbins):
                self.signalProjection[i] = signaltime.ProjectionY(str(runnumber)+str(self.channel)+"signalprojection_bin_"+str(i).zfill(2), i+1,i+1)
                self.signalProjection[i].SetTitle("Run{run}Ch{channel} Signal Projection of Bin {bin}".format(run=runnumber, channel=self.channel, bin=i))
                self.signalProjection[i].GetXaxis().SetTitle("Signal ({signal})".format(signal=self.analysis.signalname))
                binProjection_ped = pedestaltime.ProjectionY("proY_ped", i+1,i+1)
                if self.signalProjection[i].GetEntries() > 0:
                    if mode in ["mean", "Mean"]:
                        self.graph.SetPoint(count, (i+0.5)*totalMinutes/nbins, self.signalProjection[i].GetMean())
                        self.graph.SetPointError(count, 0, self.signalProjection[i].GetRMS()/ROOT.TMath.Sqrt(self.signalProjection[i].GetEntries()))
                    elif mode in ["fit", "Fit"]:
                        self.signalProjection[i].GetMaximum()
                        maxposition = self.signalProjection[i].GetBinCenter(self.signalProjection[i].GetMaximumBin())
                        self.signalProjection[i].Fit("landau", "Q","",maxposition-50,maxposition+50)
                        fitfun = self.signalProjection[i].GetFunction("landau")
                        mpv = fitfun.GetParameter(1)
                        mpverr = fitfun.GetParError(1)
                        self.graph.SetPoint(count, (i+0.5)*totalMinutes/nbins, mpv)
                        self.graph.SetPointError(count, 0, mpverr)
                    self.pedgraph.SetPoint(count, (i+0.5)*totalMinutes/nbins, binProjection_ped.GetMean())
                    self.pedgraph.SetPointError(count, 0, binProjection_ped.GetRMS()/ROOT.TMath.Sqrt(binProjection_ped.GetEntries()))
                    count += 1
                    final_i = i
                else:
                    print "bin", i, " EMPTY"

            #draw mean signal vs time
            signalpad = self.signalTimeCanvas.cd(1)
            self.graph.Fit("pol0")
            ROOT.gStyle.SetOptFit(1)
            self.graph.GetXaxis().SetTitleOffset(0.7)
            self.graph.GetXaxis().SetTitle("time / min")
            self.graph.GetXaxis().SetTitleSize(0.06)
            self.graph.GetXaxis().SetLabelSize(0.06)
            self.graph.GetXaxis().SetRangeUser(0, totalMinutes)
            if mode in ["mean", "Mean"]:
                yTitlestr = "Mean Signal ({signalname})".format(signalname=(self.analysis.signaldefinition[self.channel]) )
            elif mode in ["fit", "Fit"]:
                yTitlestr = "MPV of Signal fit ({signalname})".format(signalname=(self.analysis.signaldefinition[self.channel]) )
            # self.graph.GetYaxis().SetRangeUser(ymin, ymax)
            self.graph.GetYaxis().SetTitleOffset(0.9)
            self.graph.GetYaxis().SetTitleSize(0.06)
            self.graph.GetYaxis().SetLabelSize(0.06)
            self.graph.GetYaxis().SetTitle(yTitlestr)
            self.graph.Draw("ALP")
            if setyscale_sig!=None:
                self.graph.GetYaxis().SetRangeUser(setyscale_sig[0], setyscale_sig[1])
                self.graph.Draw()
                self.signalTimeCanvas.Update()
            signalpad.Update()
            self.padymargins["signal"] = [signalpad.GetUymin(), signalpad.GetUymax()]
            #savename= "Run{runnumber}_{diamondname}_SignalTimeEvolution".format(runnumber=self.analysis.run.run_number, diamondname=self.analysis.run.diamondname[self.channel])
            #if savePlot: self.analysis.SavePlots(savename, "eps")

            #2d distribution (high resolution)
            ROOT.gStyle.SetPalette(55) # rainbow palette
            ROOT.gStyle.SetNumberContours(200)
            pad = self.signalTimeCanvas.cd(2)
            self.analysis.run.tree.Draw((self.analysis.signaldefinition[self.channel]+":(event_number)/1000>>signaltime2d{run}{channel}({bins}, {start}, {end}, 300, 0, 500)").format(bins=nbins, run=self.analysis.run.run_number, channel=self.channel, start=startevent/1000, end=endevent/1000), self.analysis.GetCut(self.channel), drawOption2D, self.analysis.GetNEventsCut(channel=self.channel), self.analysis.GetMinEventCut(channel=self.channel))
            self.signaltime2d = gROOT.FindObject("signaltime2d{run}{channel}".format(run=self.analysis.run.run_number, channel=self.channel))
            self.signaltime2d.SetStats(0)
            self.signaltime2d.SetTitle("{signal} vs Event {cut}".format(signal=self.analysis.signaldefinition[self.channel], cut="{"+self.analysis.GetUserCutString(channel=self.channel)+"}"))
            self.signaltime2d.GetXaxis().SetLabelSize(0.06)
            self.signaltime2d.GetYaxis().SetLabelSize(0.06)
            self.signaltime2d.GetXaxis().SetTitle("event number / 1000")
            self.signaltime2d.GetXaxis().SetTitleSize(0.06)
            self.signaltime2d.GetXaxis().SetTitleOffset(0.7)
            self.signaltime2d.Draw(drawOption2D)
            self.analysis.DrawRunInfo(channel=self.channel, canvas=pad, infoid="preanalysis{run}{ch}".format(run=self.analysis.run.run_number, ch=self.channel))
            #signaltime.Draw()

            #draw mean pedestal vs time
            pedestalpad = self.signalTimeCanvas.cd(3)
            self.pedgraph.Fit("pol0")
            ROOT.gStyle.SetOptFit(1)
            self.pedgraph.GetXaxis().SetTitleOffset(0.7)
            self.pedgraph.GetXaxis().SetTitle("time / min")
            self.pedgraph.GetXaxis().SetTitleSize(0.06)
            self.pedgraph.GetXaxis().SetLabelSize(0.06)
            self.pedgraph.GetXaxis().SetRangeUser(0, totalMinutes)
            yTitlestr = "Mean Pedestal ({pedestalname})".format(pedestalname= self.analysis.pedestalname+"[{channel}]".format(channel=self.channel))
            # self.pedgraph.GetYaxis().SetRangeUser(ymin, ymax)
            self.pedgraph.GetYaxis().SetTitleOffset(0.9)
            self.pedgraph.GetYaxis().SetTitleSize(0.06)
            self.pedgraph.GetYaxis().SetLabelSize(0.06)
            self.pedgraph.GetYaxis().SetTitle(yTitlestr)
            self.pedgraph.Draw("ALP")
            if setyscale_ped!=None:
                self.pedgraph.GetYaxis().SetRangeUser(setyscale_ped[0], setyscale_ped[1])
                self.pedgraph.Draw()
                self.signalTimeCanvas.Update()
            pedestalpad.Update()
            self.padymargins["pedestal"] = [pedestalpad.GetUymin(), pedestalpad.GetUymax()]
            #savename= "Run{runnumber}_{diamondname}_PedestalTimeEvolution.eps".format(runnumber=self.analysis.run.run_number, diamondname=self.analysis.run.diamondname[self.channel])
            #self.analysis.SavePlots(savename)

        else:

            if not bool(self.signalTimeCanvas):
                self.signalTimeCanvas = ROOT.TCanvas("signalTimeCanvas"+"Ch"+str(self.channel), "signalTimeCanvas"+"Ch"+str(self.channel), 650, 700)
                self.signalTimeCanvas.Divide(1,3)

            self.signalTimeCanvas.cd(1)
            if setyscale_sig!=None:
                self.graph.GetYaxis().SetRangeUser(setyscale_sig[0], setyscale_sig[1])
                self.graph.Draw()
            else:
                self.graph.Draw()

            self.signalTimeCanvas.cd(2)
            self.signaltime2d.Draw(drawOption2D)

            self.signalTimeCanvas.cd(3)
            if setyscale_ped!=None:
                self.pedgraph.GetYaxis().SetRangeUser(setyscale_ped[0], setyscale_ped[1])
                self.pedgraph.Draw()
            else:
                self.pedgraph.Draw()

        #update canvas
        self.signalTimeCanvas.Update()
        savename = "Run{run}_PreAnalysis_{diamond}".format(run=self.analysis.run.run_number, diamond=self.analysis.run.diamondname[self.channel])
        print "SAVENAME: ", savename
        if savePlot:
            self.SavePlots(savename, "png", canvas=self.signalTimeCanvas, subDir=self.analysis.run.diamondname[self.channel])
            self.SavePlots(savename, "root", canvas=self.signalTimeCanvas, subDir="root")

        self.analysis.IfWait("showing MakePreAnalysis plots..")

