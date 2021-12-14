"""
Load, analyze, and save a folder of abf files.

"""

import os
import time
import pandas as pd
import numpy as np
import scipy.signal
import pyabf

# for baseline
from scipy import sparse
from scipy.sparse.linalg import spsolve

import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import ipywidgets as widgets
import IPython.display

import matplotlib as mpl
mpl.rcParams['axes.spines.right'] = False
mpl.rcParams['axes.spines.top'] = False

import colinUtils

import sanpy.interface.plugins.stimGen2
from sanpy.interface.plugins.stimGen2 import readFileParams, buildStimDict

from sanpy.sanpyLogger import get_logger
logger = get_logger(__name__)

class bAnalysis2:
	"""
	Manager one abf loaded from a file
	"""
	def getStatList():
		"""
		get list of stats corresponding to df columns. Used to plot scatter

		this is intentionally 'static', use like
			statList = bAnalysis2.getStatList
		"""
		statList = [
					'index',
					'file',
					'genotype',
					'sex',
					'userType',
					'DAC0',
					'peak_sec',
					'peak_val',
					'foot_sec',
					'foot_val',
					'myHeight',
					'riseTime_ms',
					'hw20_width_ms',
					'hw50_width_ms',
					'hw80_width_ms',
					'ipi_ms',
					'instFreq_hz',
					'file_idx',  # added when we group df across a folder
					'master_idx',  # added when we group df across a folder
					]
		return statList

	def getDefaultDetection():
		 # detect peaks (peak, prominence, width)
		detectionDict = {
			'condition': '',
			'genotype': '',
			'sex': '',
			'doMedian': False,
			'medianFilter' : 5,  # points, must be odd. IF 0 then no median filter
			'doSavitzkyGolay': True,
			'SavitzkyGolay_pnts': 11,
			'SavitzkyGolay_poly': 5,
			'doBaseline': True,
			'lam_baseline': 1e13,  # for _baseline_als_optimized
			'p_baseline': 0.5, # for _baseline_als_optimized
			'preFootMs': 5,
			'threshold' : 4, #6, #3,  # minimum height
			'distance': 250,  # minimum number of points between peaks
			#'prominence': None, #10,  # could also be [min, max]
			'wlen': 1500,
			'width': [50, 500],  # [min, max] required
			'halfWidths': [20, 50, 80],
			'fullWidthFraction': 0.75,  # for initial peak detection with SciPy
			'startSec': None,  # limit detection to a range of x
			'stopSec': None,  # limit detection to a range of x

			'verbose': False,
		}
		return detectionDict

	def __init__(self, path, stimulusFileFolder=None):
		"""
		path (str): path to abf file
		stimulusFileFolder (str): Relative path to stimulus file.
								Leave as None, and assume stimulus file atf are in same folder as abf
		"""
		self._path = path
		self._abf = pyabf.ABF(path, stimulusFileFolder=stimulusFileFolder)
		self._detectionParams = bAnalysis2.getDefaultDetection()
		self._analysisDf = None

		# needs to be a list to account for sweaps
		self._sweepY_filtered = [None] * self.numSweeps

		self._currentSweep = 0

		#
		# if we were recorded with a stimulus file abf
		# needed to assign stimulusWaveformFromFile
		tmpSweepC = self.abf.sweepC
		stimFilePath, stimFileComment = pyabf.stimulus.abbCommentFromFile(self.abf)
		if stimFileComment is None:
			self._stimDict = None
			self._stimFile = None
		else:
			self._stimFile = stimFilePath
			self._stimDict = sanpy.interface.plugins.stimGen2.readCommentParams(stimFileComment)

	@property
	def stimDict(self):
		"""
		If recorded with a stimulus file, return dict of stimulus parameters.
		Stimulus parameters are defined in sanpy/interface/plugins/stimGen2.py
		"""
		return self._stimDict

	def reduce(self):
		"""
		Reduce spikes based on start/stop of sin stimulus

		TODO:
			Use readFileParams(atfPath) to read stimulus ATF file and get start/stop

		Return:
			df of spikes within sin stimulus
		"""
		df = self.analysisDf
		if self.stimDict is not None:
			#print(ba.stimDict)
			stimStartSeconds = self.stimDict['stimStartSeconds']
			durSeconds = self.stimDict['durSeconds']
			startSec = stimStartSeconds
			stopSec = startSec + durSeconds
			try:
				df = df[ (df['peak_sec']>=startSec) & (df['peak_sec']<=stopSec)]
			except (KeyError) as e:
				logger.error(e)
		#
		return df

	def stimFileDict(self):
		d = self.stimDict
		if d is None:
			return

		dList = buildStimDict(d, path=self.filePath)
		#for one in dList:
		#	print(one)
		df = pd.DataFrame(dList)
		return df

	def isiStats(self, hue='sweep'):
		df = self.analysisDf
		if df is None:
			return pd.DataFrame()  # empty

		df = self.reduce()  # reduce based on start/stop of sin stimulus

		statList = []

		statStr = 'ipi_ms'

		stimFileDict = self.stimFileDict()
		'''
		if stimFileDict is not None:
			print('stimFileDict:')
			print(stimFileDict)
		'''

		hueList = df[hue].unique()
		for idx,oneHue in enumerate(hueList):
			dfPlot = df[ df[hue]==oneHue ]
			ipi_ms = dfPlot[statStr]

			meanISI = np.nanmean(ipi_ms)
			stdISI = np.nanstd(ipi_ms)
			cvISI = stdISI / meanISI
			cvISI = round(cvISI, 3)
			cvISI_inv = np.nanstd(1/ipi_ms) / np.nanmean(1/ipi_ms)
			cvISI_inv = round(cvISI_inv, 3)

			oneDict = {
				'file': self.fileName,
				'stat': statStr,
				'count': len(ipi_ms),
				'minISI': round(np.nanmin(ipi_ms),3),
				'maxISI': round(np.nanmax(ipi_ms),3),
				'stdISI': round(stdISI,3),
				'meanISI': round(np.nanmean(ipi_ms),3),
				'medianISI': round(np.nanmedian(ipi_ms),3),
				'cvISI': cvISI,
				'cvISI_inv': cvISI_inv,

				# stim params from stimulus file
				'Stim Freq (Hz)': '',
				'Stim Amp': '',
				'Noise Amp': '',

			}

			if stimFileDict is not None:
				oneDict['Stim Freq (Hz)'] = stimFileDict.loc[idx, 'freq(Hz)']
				oneDict['Stim Amp'] = stimFileDict.loc[idx, 'amp']
				oneDict['Noise Amp'] = stimFileDict.loc[idx, 'noise amp']

			statList.append(oneDict)

		#
		retDf = pd.DataFrame(statList)
		return retDf

	def setSweep(self, sweep):
		"""
		Set the current sweep
		"""
		self._currentSweep = sweep
		self.abf.setSweep(sweep)

	def __str__(self):
		dur = round(self.sweepDur,2)

		stimFileStr = ''
		if self._stimFile is not None:
			stimFileStr = f'stimFile:{os.path.split(self._stimFile)[1]}'

		s = f'{self.fileName} sweeps:{self.numSweeps} dur(s):{dur} kHz:{self.dataPointsPerMs} {stimFileStr} events:{self.numPeaks}'

		return s

	def getHeader(self):
		"""
		Return important parameters as a dict
		"""
		startSec = self.detectionParams['startSec']
		stopSec = self.detectionParams['stopSec']

		if startSec is None:
			startSec = 0
		if stopSec is None:
			stopSec = round(self.sweepDur,3)

		theRet = {
			'File': self.fileName,
			'Sweeps': self.numSweeps,
			'Dur(s)': round(self.sweepDur,3),
			'kHz': self.dataPointsPerMs,

			# add back in
			#'Start(s)': startSec,
			#'Stop(s)': stopSec,

			# if we have a atfStim stimulus file
			'Stim Freq (Hz)': '',
			'Stim Amp': '',
			'Noise Amp': '',
			'Noise Step': '',

			'Detection Threshold': self.detectionParams['threshold'],
			'Num Peaks': self.numPeaks,
		}

		if self._stimDict is not None:
			try:
				theRet['Stim Freq (Hz)'] = self._stimDict['stimFreq']
				theRet['Stim Amp'] = self._stimDict['stimAmp']
				theRet['Noise Amp'] = self._stimDict['stimNoiseAmp']
				theRet['Noise Step'] = self._stimDict['stimNoiseStep']
			except (KeyError) as e:
				logger.warning(f'Did not find keys (stimNoiseAmp, stimNoiseStep)')
		return theRet

	def save(self):
		folderPath, filename = os.path.split(self._path)

		resultsFile = os.path.splitext(filename)[0] + '_full.csv'
		resultsPath = os.path.join(folderPath, resultsFile)
		self.analysisDf.to_csv(resultsPath)

		return resultsPath

	def getValue(self, col:str, rowIdx:int = None):
		"""
		rowIdx (int or None): If None then all rows
		"""
		theRet = None
		try:
			if rowIdx is None:
				return self.analysisDf[col]
			else:
				return self.analysisDf.iloc[rowIdx][col]
		except (KeyError) as e:
			print(f'My Key Error in getStat() {rowIdx} {col}')

	def setValue(self, rowIdx:int, col:str, value):
		try:
			self.analysisDf.loc[rowIdx, col] = value
		except (KeyError) as e:
			print(f'My Key Error in getStat() {rowIdx} {col}')

	@property
	def detectionParams(self):
		return self._detectionParams

	@property
	def filePath(self):
		return self._path

	@property
	def fileName(self):
		return os.path.split(self._path)[1]

	@property
	def abf(self):
		return self._abf

	@property
	def dataPointsPerMs(self):
		return self.abf.dataPointsPerMs

	@property
	def numSweeps(self):
		return len(self.abf.sweepList)

	@property
	def sweepList(self):
		return self.abf.sweepList

	@property
	def sweepDur(self):
		return self.abf.sweepX[-1]

	@property
	def sweepX(self):
		return self.abf.sweepX

	@property
	def sweepY(self):
		return self.abf.sweepY

	@property
	def sweepC(self):
		return self.abf.sweepC

	@property
	def sweepY_filtered(self):
		"""
		TODO: need to expand for multiple sweeps
		"""
		return self._sweepY_filtered[self._currentSweep]

	@property
	def analysisDf(self):
		return self._analysisDf

	@property
	def numPeaks(self):
		if self.analysisDf is None:
			return None
		else:
			return len(self.analysisDf)

	def detect(self, detectionDict=None):
		"""
		Detect one file
		"""
		logger.info(f'Starting detection for {self.filePath}')

		if detectionDict is None:
			detectionDict = bAnalysis2.getDefaultDetection()

		self._detectionParams = detectionDict

		self._analysisDf = None  # we will fill this in

		for sweep in self.abf.sweepList:
			self.detect_(sweep)

	def detect_(self, sweep):
		"""
		Detect one file
		"""

		#self.abf.setSweep(sweep)
		self.setSweep(sweep)

		detectionDict = self._detectionParams

		# detect peaks (peak, prominence, width)
		doMedian = detectionDict['doMedian']
		medianFilter = detectionDict['medianFilter']
		doSavitzkyGolay = detectionDict['doSavitzkyGolay']
		SavitzkyGolay_pnts = detectionDict['SavitzkyGolay_pnts']
		SavitzkyGolay_poly = detectionDict['SavitzkyGolay_poly']
		threshold = detectionDict['threshold']
		distance = detectionDict['distance']
		wlen = detectionDict['wlen']
		width = detectionDict['width']
		fullWidthFraction = detectionDict['fullWidthFraction']
		#xRange = detectionDict['xRange']
		startSec = detectionDict['startSec']
		stopSec = detectionDict['stopSec']
		verbose = detectionDict['verbose']

		sweepY_filtered = self.sweepY_filtered
		if sweepY_filtered is None:
			#print('filtering for sweep:', sweep)
			sweepY_filtered = self.sweepY
			if doMedian:
				sweepY_filtered = scipy.signal.medfilt(sweepY_filtered, medianFilter)
			if doSavitzkyGolay:
				sweepY_filtered = scipy.signal.savgol_filter(sweepY_filtered,
									SavitzkyGolay_pnts, SavitzkyGolay_poly,
									mode='nearest', axis=0)
			# baseline subtract
			if detectionDict['doBaseline']:
				print('PERFORMING BASELINE')
				lam = detectionDict['lam_baseline']  # 1e13
				p = detectionDict['p_baseline']  # 0.5
				z = self._baseline_als_optimized(sweepY_filtered, lam, p, niter=10)
				sweepY_filtered = sweepY_filtered - z

			#
			self._sweepY_filtered[self._currentSweep] = sweepY_filtered

		#
		# find peaks
		if startSec is None:
			startSec = 0
		if stopSec is None:
			stopSec = self.sweepDur
		xMask = (self.sweepX>=startSec) & (self.sweepX<=stopSec)
		firstPnt = np.where(xMask==True)[0][0]

		peaks, _properties = scipy.signal.find_peaks(sweepY_filtered[xMask],
								height=threshold,
								distance=distance, prominence=None,
								wlen=None, width=width)
		peaks += firstPnt

		numPeaks = len(peaks)

		if numPeaks < 2:
			# ABORT
			print('error: did not detect enough peaks', numPeaks)
			return

		df = pd.DataFrame()  # new DataFrame for this sweep

		df['index'] = [x for x in range(numPeaks)]
		df['file'] = [self.fileName] * numPeaks
		df['condition'] = [detectionDict['condition']] * numPeaks
		df['genotype'] = [detectionDict['genotype']] * numPeaks
		df['sex'] = [detectionDict['sex']] * numPeaks
		df['accept'] = [True] * numPeaks  # analysis['accept']
		df['userType'] = [0] * numPeaks  # analysis['accept']

		df['DAC0'] = self.sweepC[peaks]
		df['sweep'] = sweep  # abb working on stach-analysis
		df['peak_pnt'] = peaks
		df['peak_sec'] = self._pnt2Sec(peaks)
		df['peak_val'] = sweepY_filtered[peaks]

		# critical
		#self._analysisDf = df  # TODO: sloppy, fix this

		#
		self._getFeet(df)

		# inst freq and (inst) isi
		peakSec = df['peak_sec']
		instFreq_hz = 1 / np.diff(peakSec)
		instFreq_hz = np.insert(instFreq_hz, 0, np.nan)

		ipi_ms = np.diff(peakSec) * 1000
		ipi_ms = np.insert(ipi_ms, 0, np.nan)

		df['ipi_ms'] = ipi_ms
		df['instFreq_hz'] = instFreq_hz

		#
		df['userNote'] = [''] * numPeaks

		# detection parameters used as columns
		for k,v in detectionDict.items():
			detectionKey = 'd_' + k
			if isinstance(v, list):
				v = str(v)
			df[detectionKey] = v

		df['filePath'] = self._path

		# critical
		if self._analysisDf is None:
			# first sweep
			#print('creating from df:', len(df))
			self._analysisDf = df
		else:
			#print('appending new df', len(df))
			self._analysisDf = self._analysisDf.append(df, ignore_index=True)

		#if verbose:
		#if 1:
		#	print('self._analysisDf is now:', len(self._analysisDf))

	def _getFeet(self, df):
		"""
		df (DataFrame): The current dataframe we are working on
		"""

		#df = self.analysisDf

		peaks = df['peak_pnt']

		verbose = self._detectionParams['verbose']

		wlen = self._detectionParams['wlen']
		fullWidthFraction = self._detectionParams['fullWidthFraction']
		# full height to then get foot
		# [0] is width, [1] heights, [2] is start, [3] is stop
		fullWidth = scipy.signal.peak_widths(self.sweepY_filtered, peaks,
							wlen=wlen, rel_height=fullWidthFraction)

		fullWidth_left_pnt = fullWidth[2]  # FRACTIONAL POINTS

		# store this for debugging detection
		fullWidth_left_pnt2 = np.round(fullWidth_left_pnt).astype(int)
		fullWidth_left_val = self.sweepY_filtered[fullWidth_left_pnt2]
		df['fullWidth_left_pnt'] = fullWidth_left_pnt2
		df['fullWidth_left_val'] = fullWidth_left_val

		# using the derivstive to find zero crossing before
		# original full width left point
		yFull = self.sweepY_filtered
		yDiffFull = np.diff(yFull)
		yDiffFull = np.insert(yDiffFull, 0, np.nan)

		footPntList = []
		footSec = []
		yFoot = []
		myHeight = []
		preMs = self._detectionParams['preFootMs']
		prePnts = self._sec2Pnt(preMs/1000)
		for idx,footPnt in enumerate(fullWidth_left_pnt):
			footPnt = round(footPnt)  # footPnt is in fractional points
			lastCrossingPnt = footPnt
			# move forwared a bit in case we are already in a local minima ???
			footPnt += 2  # TODO: add as param
			preStart = footPnt - prePnts
			preClip = yDiffFull[preStart:footPnt]
			zero_crossings = np.where(np.diff(np.sign(preClip)))[0]
			xLastCrossing = self._pnt2Sec(footPnt)  # defaults
			yLastCrossing = self.sweepY_filtered[footPnt]
			if len(zero_crossings)==0:
				if verbose:
					tmpSec = round(self._pnt2Sec(footPnt), 3)
					print('  error: no foot for peak', idx, 'sec:', tmpSec, 'did not find zero crossings')
			else:
				#print(idx, 'footPnt:', footPnt, zero_crossings, preClip)
				lastCrossingPnt = preStart + zero_crossings[-1]
				xLastCrossing = self._pnt2Sec(lastCrossingPnt)
				# get y-value (pA) from filtered. This removes 'pops' in raw data
				yLastCrossing = self.sweepY_filtered[lastCrossingPnt]

			#
			footPntList.append(lastCrossingPnt)
			footSec.append(xLastCrossing)
			yFoot.append(yLastCrossing)

			peakPnt = df.loc[idx, 'peak_pnt']
			peakVal = self.sweepY_filtered[peakPnt]
			height = peakVal - yLastCrossing
			#print(f'idx {idx} {peakPnt} {peakVal} - {yLastCrossing} = {height}')
			myHeight.append(height)

		#
		#df =self._analysisList[self._analysisIdx]['results_full']
		df['foot_pnt'] = footPntList  # sec
		df['foot_sec'] = footSec  # sec
		df['foot_val'] = yFoot  # pA
		df['myHeight'] = myHeight

		#
		# half-width
		#numPeaks = self.numPeaks
		numPeaks = len(df)
		halfWidths = self._detectionParams['halfWidths']
		maxWidthPnts = self._detectionParams['distance']
		maxWidthSec = self._pnt2Sec(maxWidthPnts)

		for halfWidth in halfWidths:
			leftList = [None] * numPeaks
			rightList = [None] * numPeaks
			heightList = [None] * numPeaks
			widthList = [None] * numPeaks
			for idx,pnt in enumerate(df['peak_pnt']):
				xFootSec = df.loc[idx, 'foot_sec']
				yFootVal = df.loc[idx, 'foot_val']
				peakSec = df.loc[idx, 'peak_sec']
				peakVal = df.loc[idx, 'peak_val']
				halfHeight = yFootVal + (peakVal - yFootVal) * (halfWidth * 0.01)

				startSec = xFootSec
				startPrePnt = self._sec2Pnt(startSec)
				stopSec = peakSec # xFootSec + maxWidthSec
				preClipMask = (self.sweepX>=startSec) & (self.sweepX<=stopSec)
				preClip = self.sweepY_filtered[preClipMask]

				startSec = peakSec
				startPostPnt = self._sec2Pnt(startSec)
				stopSec = startSec + maxWidthSec
				postClipMask = (self.sweepX>=startSec) & (self.sweepX<=stopSec)
				postClip = self.sweepY_filtered[postClipMask]

				#if halfWidth == 50:
				#	print(idx, halfWidth, yFootVal, peakVal, halfHeight)
				threshold_crossings = np.diff(preClip > halfHeight, prepend=False)
				upward = np.argwhere(threshold_crossings)[::2,0]  # Upward crossings

				if len(upward > 0):
					firstUpPnt = startPrePnt + upward[0]
					leftList[idx] = self._pnt2Sec(firstUpPnt)

				threshold_crossings = np.diff(postClip > halfHeight, prepend=False)
				downward = np.argwhere(threshold_crossings)[1::2,0]  # Downward crossings
				if len(downward > 0):
					lastDownPnt = startPostPnt + downward[-1]
					rightList[idx] = self._pnt2Sec(lastDownPnt)

				if len(upward > 0) and len(downward > 0):
					heightList[idx] = halfHeight
					widthList[idx] = (rightList[idx] - leftList[idx]) * 1000

			#
			keyBase = 'hw' + str(halfWidth) + '_'
			df[keyBase+'width_ms'] = widthList
			df[keyBase+'left_sec'] = leftList
			df[keyBase+'right_sec'] = rightList
			df[keyBase+'val'] = heightList # y val of height

			#
			# rise time ms
			df['riseTime_ms'] = (df['peak_sec'] - df['foot_sec']) * 1000

	def _baseline_als_optimized(self, y, lam, p, niter=10):
		"""
		p for asymmetry and lam for smoothness.
		generally:
			0.001 ≤ p ≤ 0.1
			10^2 ≤ lam ≤ 10^9
		"""
		start = time.time()

		L = len(y)
		D = sparse.diags([1,-2,1],[0,-1,-2], shape=(L,L-2))
		D = lam * D.dot(D.transpose()) # Precompute this term since it does not depend on `w`
		w = np.ones(L)
		W = sparse.spdiags(w, 0, L, L)
		for i in range(niter):
			W.setdiag(w) # Do not create a new matrix, just update diagonal values
			Z = W + D
			z = spsolve(Z, w*y)
			w = p * (y > z) + (1-p) * (y < z)

		stop = time.time()
		#print(f'  _baseline_als_optimized() took {round(stop-start, 3)} seconds')
		return z

	def _pnt2Sec(self, pnt):
		dataPointsPerMs = self.dataPointsPerMs
		if isinstance(pnt, list):
			return [onePnt / dataPointsPerMs / 1000 for onePnt in pnt]
		else:
			return pnt / dataPointsPerMs / 1000

	def _sec2Pnt(self, sec):
		"""
		Returns:
			point(s) as int(s)
		"""
		dataPointsPerMs = self.dataPointsPerMs
		if isinstance(sec, list):
			return [round(onePnt * 1000 * dataPointsPerMs) for onePnt in sec]
		elif isinstance(sec, np.ndarray):
			ms = sec * 1000 * dataPointsPerMs
			pnt = np.around(ms).astype(int)
			return pnt
		else:
			#print('ERROR: _sec2Pnt() got unexpected type:', type(sec))
			return round(sec * 1000 * dataPointsPerMs)

class colinAnalysis2:
	"""
	Manage a list of bAnalysis2 (abf files) loaded from a folder
	"""
	def __init__(self, folderPath=None):
		self._folderPath = folderPath

		self._analysisList = []
		# list of bAnalysis2

		self._analysisIdx = 0  # the first abf

		self.loadFolder()

	def __iter__(self):
		self._iterIdx = 0
		return self

	def __next__(self):
		if self._iterIdx < self.numFiles:
			x = self._analysisList[self._iterIdx]
			self._iterIdx += 1
			return x
		else:
			raise StopIteration

	def asDataFrame(self):
		"""
		Get information for each file as a DataFrame
		"""
		headerList = []
		for fileIdx in range(self.numFiles):
			file = self.getFile(fileIdx)
			oneHeader = file.getHeader()
			headerList.append(oneHeader)
		df = pd.DataFrame(headerList)
		return df

	@property
	def folderPath(self):
		return self._folderPath

	@property
	def fileList(self):
		return [ba.fileName for ba in self._analysisList]

	@property
	def numFiles(self):
		return len(self._analysisList)

	def getFile(self, idx):
		return self._analysisList[idx]

	def loadFolder(self, path=None):
		logger.info(path)
		if path is None:
			path = self.folderPath
		if path is None:
			return

		fileList = sorted(os.listdir(path))
		print(path, fileList)

		if len(fileList) == 0:
			# warn user
			pass

		self._folderPath = path
		self._analysisList = []  # DELETE EXISTING

		for file in fileList:
			if file.startswith('.'):
				continue
			if file.endswith('.abf'):
				filePath = os.path.join(self.folderPath, file)
				oneAnalysis = bAnalysis2(filePath)
				logger.info(oneAnalysis)
				self._analysisList.append(oneAnalysis)

	def refreshFolder(self):
		"""
		Look in folderPath for new files not in our existing list.
		Append to files to end of list

		Return:
			int: Number of new files.
		"""
		logger.info('')
		existingFileList = self.fileList
		print('  ', existingFileList)
		newFileList = sorted(os.listdir(self.folderPath))
		numNewFiles = 0
		for newFile in newFileList:
			if newFile.startswith('.'):
				continue
			if newFile.endswith('.abf'):
				if not newFile in existingFileList:
					print('  new file:', newFile)
					# load and append new file to self._analysisList
					newFilePath = os.path.join(self.folderPath, newFile)
					oneAnalysis = bAnalysis2(newFilePath)
					logger.info(f'  {oneAnalysis}')
					self._analysisList.append(oneAnalysis)
					numNewFiles += 1
		#
		logger.info(f'Added {numNewFiles} files')
		return numNewFiles

	def getAllDataFrame(self):
		"""Get analysis results for all files.
		"""
		df = None
		totalNum = 0
		for idx, ba in enumerate(self._analysisList):
			oneDf = ba.analysisDf
			if oneDf is None:
				print(f'   skipping file {idx}, no analysis')
				continue

			# add some columns
			oneDf['file_idx'] = idx
			oneDf['master_idx'] = [totalNum+x for x in range(len(oneDf))]  # todo: improve efficiency

			if df is None:
				df = oneDf
			else:
				df = df.append(oneDf, ignore_index=True)

			totalNum += len(oneDf)
		#
		return df

def testColin():
	'''
	path = '/media/cudmore/data/colin/21n10003.abf'
	ba2 = bAnalysis2(path)
	ba2.detect()
	'''

	path = '/media/cudmore/data/colin'
	ca = colinAnalysis(path)
	ca._analysisIdx = 0
	ca.detect()

	'''
	a = ca.getAnalysis()
	for k,v in a.items():
		if isinstance(v, dict):
			print(k, 'dict')
			for k2,v2 in v.items():
				print('  ', k2, ':', v2)
		elif isinstance(v, tuple):
			print(k, 'tuple', '[0] width, [1] heights, [2] start, [3] stop')
			for idx,item in enumerate(v):
				print('  ', idx, ':', item)
		else:
			print(k, ':', v)
	'''

	#ca.testPlot()
	onePeak = None
	zoomSec = None
	ca.plotOne(onePeak=onePeak, zoomSec=zoomSec)

	#
	plt.show()

	print(ca.getDataFrame().head())
	#print(ca.getDataFrame()['myHeight'])

	#print(ca)
	#ca.myShow()

	#print(ca.getAnalysis())

	# test save
	#ca.save()

if __name__ == '__main__':
	testColin()