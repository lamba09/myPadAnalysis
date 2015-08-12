from Helper.Initializer import initializer
from Runinfos.RunInfo import RunInfo
from DiamondClass import Diamond
from Elementary import Elementary
import ROOT
import os
import ConfigParser
import json
import copy

dummyinfo =  {
        "persons on shift": "-",
        "run info": "-",
        "type": "signal",
        "configuration": "signal",
        "mask": "-",
        "masked pixels": 0,
        "diamond 1": "diamond",
        "diamond 2": "diamond",
        "hv dia1": 0,
        "hv dia2": 0,
        "fs11": 0,
        "fsh13": 0,
        "quadrupole": "-",
        "analogue current": 0,
        "digital current": 0,
        "begin date": "-/-/-",
        "trim time": "-:-:-",
        "config time": "-:-:-",
        "start time": "-:-:-",
        "trig accept time": "-:-:-",
        "opening time": "-:-:-",
        "open time": "-:-:-",
        "stop time": "-:-:-",
        "raw rate": 0,
        "prescaled rate": 0,
        "to TLU rate": 0,
        "pulser accept rate": 0,
        "cmspixel events": 0,
        "drs4 events": 0,
        "datacollector events": 0,
        "aimed flux": 0,
        "measured flux": 0,
        "user comments": "-"
}

class Run(Elementary):
    '''

    '''

    current_run = {}
    operationmode = ''
    TrackingPadAnalysis = {}

    def __init__(self, run_number, channels=3, validate = False, verbose = False):
        '''

        :param run_number: number of the run
        :param channels: 0x1=ch0; 0x2=ch3
        :param validate:
        :param verbose:
        :return:
        '''
        Elementary.__init__(self, verbose=verbose)
        assert(channels>=1 and channels<=3), "invalid channel number: 0x1=ch0; 0x2=ch3"
        self.run_number = -1
        self.LoadConfig()

        if validate:
            self.ValidateRuns()

        if run_number != None:
            assert(run_number > 0), "incorrect run_number"
            self.SetRun(run_number)
        else:
            self.LoadRunInfo()
        self.diamondname = {
            0: str(self.RunInfo["diamond 1"]),
            3: str(self.RunInfo["diamond 2"])
        }
        self.bias = {
            0: self.RunInfo["hv dia1"],
            3: self.RunInfo["hv dia2"]
        }
        self.analyzeCh = {
            0: (channels & 1<<0) == 1<<0,
            3: (channels & 1<<1) == 1<<1
        }
        self.IsMonteCarlo = False

    def LoadConfig(self):
        machineConfigParser = ConfigParser.ConfigParser()
        machineConfigParser.read('Configuration/Machineconfig.cfg')
        self.operationmode = machineConfigParser.get('EXEC-MACHINE','operationmode')
        self.ShowAndWait = False
        runConfigParser = ConfigParser.ConfigParser()
        runConfigParser.read('Configuration/RunConfig.cfg')
        self.filename = runConfigParser.get('BASIC', 'filename')
        self.treename = runConfigParser.get('BASIC', 'treename')
        self.sshrunpath = runConfigParser.get('BASIC', 'runpath')
        self.runinfofile = runConfigParser.get('BASIC', 'runinfofile')

    def LoadRunInfo(self):
        self.RunInfo = {}
        try:
            f = open(self.runinfofile, "r")
            data = json.load(f)
            f.close()
            self.allRunKeys = copy.deepcopy(data.keys())
            loaderror = False
        except IOError:
            print "WARNING: unable to load json file:\n\t{file}".format(file=self.runinfofile)
            loaderror = True

        if self.run_number >= 0:
            if not loaderror:
                self.RunInfo = data.get("150500"+str(self.run_number).zfill(3))
            else:
                self.RunInfo = dummyinfo
            self.current_run = self.RunInfo
            if self.RunInfo is None:
                self.RunInfo = {}
                print "\nWARNING: No RunInfo could be loaded from file! \n"
                return 0
            else:
                return 1
        else:
            return 0

    def ValidateRuns(self, list_of_runs = None):
        if list_of_runs != None:
            runs = list_of_runs
        else:
            runs = RunInfo.runs.keys() # list of all runs
        self.VerbosePrint("Validating runs: ",runs)
        for run in runs:
            self.ValidateRun(run)

    def ValidateRun(self,run_number):
        self.SetRun(run_number)
        if not os.path.exists(self.TrackingPadAnalysis['ROOTFile']):
            del RunInfo.runs[run_number]
            print "INFO: path of run number ",run_number, " not found."
            return False
        else:
            return True

    def ResetMC(self):
        pass

    def SetRun(self, run_number, validate = False, loadROOTFile = True):
        if validate:
            boolfunc = self.ValidateRun
        else:
            boolfunc = lambda run: True
        assert(run_number > 0), "incorrect run_number"
        if True or run_number in RunInfo.runs and boolfunc(run_number):
            self.run_number = run_number
            self.LoadRunInfo()

            if self.operationmode == "local-ssh":
                fullROOTFilePath = '/Volumes'+self.sshrunpath+'/'+self.filename+str(run_number).zfill(3)+'.root'
                self.TrackingPadAnalysis['ROOTFile'] = fullROOTFilePath

            if self.operationmode == "ssh":
                fullROOTFilePath = self.sshrunpath+'/'+self.filename+str(run_number).zfill(3)+'.root'
                self.TrackingPadAnalysis['ROOTFile'] = fullROOTFilePath

            if self.operationmode == "local":
                self.TrackingPadAnalysis['ROOTFile'] = 'runs/run_'+str(run_number)+'/'+self.filename+str(run_number).zfill(3)+'.root'


 #           self.RunInfo = self.current_run.copy()
            #a = self.current_run.__dict__
#            self.diamond = Diamond( self.current_run['diamond'])

            self.ResetMC()
            #self.diamond = diamond # diamond is of type Diamond
            #RunInfo.__init__(self,*args)

            if loadROOTFile:
                print "LOADING: ", fullROOTFilePath
                self.rootfile = ROOT.TFile(fullROOTFilePath)
                self.tree = self.rootfile.Get(self.treename) # Get TTree called "track_info"

            assert(bool(self.tree) and bool(self.rootfile)), "Could not load root file: \n\t"+fullROOTFilePath

            #self.diamond.SetName(self.runs[0]['diamond'])
            return True
        else:
            return False

    def GetChannels(self):
        return [i for i in self.analyzeCh.keys() if self.analyzeCh[i]]
