'''
Author: Robert H Cudmore
Date: 20190225

The bAnalysis class wraps a pyabf file and adds spike detection and plotting.

Instantiate a bAnalysis object with a .abf file name

The underlying pyabf object is always available as self.abf

Usage:
	ba = bAnalysis('data/19114001.abf')
	print(ba) # prints info about underlying abf file
	ba.plotDeriv()
	ba.spikeDetect(dVthresholdPos=100)
	ba.plotSpikes()
	ba.plotClips()

Detection:
	spikeDetect0() does threshold detection to generate a list of spike times
	spikeDetect() takes a list of spike times and performs detailed analysis on each spike
Reports:
	report() and report2() generate pandas data frames of the results and can easily by manipulated or saved
Plots:
	Plot vm, derivative, spike stats etc
'''

import os, math, time
import collections

import numpy as np
import pandas as pd

import scipy.signal

import matplotlib.pyplot as plt

import pyabf # see: https://github.com/swharden/pyABF

class bAnalysis:
	def __init__(self, file=None):
		self.file = file
		self._abf = None

		self.spikeDict = [] # a list of dict

		self.spikeTimes = [] # created in self.spikeDetect()
		self.spikeClips = [] # created in self.spikeDetect()

		if not os.path.isfile(file):
			print('error: bAnalysis.__init__ file does not exist "' + file + '""')
			return None

		self._abf = pyabf.ABF(file)

		self.currentSweep = None
		self.setSweep(0)

		self.filteredVm = []
		self.filteredDeriv = []
		self.spikeTimes = []

		# keep track of the number of errors during spike detection
		self.numErrors = 0
		
	############################################################
	# access to underlying pyabf object (self.abf)
	############################################################
	@property
	def abf(self):
		return self._abf

	@property
	def dataPointsPerMs(self):
		return self.abf.dataPointsPerMs

	@property
	def sweepList(self):
		return self.abf.sweepList

	def setSweep(self, sweepNumber):
		if sweepNumber not in self.abf.sweepList:
			print('error: bAnalysis.setSweep() did not find sweep', sweepNumber, ', sweepList =', self.abf.sweepList)
		else:
			self.currentSweep = sweepNumber
			self.abf.setSweep(sweepNumber)

	@property
	def numSpikes(self):
		"""Returns the number of spikes, assumes self.spikeDetect(dVthreshold)"""
		return len(self.spikeTimes)

	@property
	def numSpikeErrors(self):
		return self.numErrors


	############################################################
	# spike detection
	############################################################
	def spikeDetect0(self, dVthresholdPos=100, medianFilter=0, startSeconds=None, stopSeconds=None):
		"""
		look for threshold crossings (dVthresholdPos) in first derivative (dV/dt) of membrane potential (Vm)
		tally each threshold crossing (e.g. a spike) in self.spikeTimes list
		
		Returns:
			self.thresholdTimes (pnts): the time of each threshold crossing
			self.spikeTimes (pnts): the time before each threshold crossing when dv/dt crosses 15% of its max
		"""
		
		print('bAnalysis.spikeDetect0() dVthresholdPos:', dVthresholdPos, 'medianFilter:', medianFilter, 'startSeconds:', startSeconds, 'stopSeconds:', stopSeconds)

		startPnt = 0
		stopPnt = len(self.abf.sweepX) - 1
		secondsOffset = 0
		if startSeconds is not None and stopSeconds is not None:
			startPnt = self.dataPointsPerMs * (startSeconds*1000) # seconds to pnt
			stopPnt = self.dataPointsPerMs * (stopSeconds*1000) # seconds to pnt
		'''
		print('   startSeconds:', startSeconds, 'stopSeconds:', stopSeconds)
		print('   startPnt:', startPnt, 'stopPnt:', stopPnt)
		'''
		
		if medianFilter > 0:
			self.filteredVm = scipy.signal.medfilt(self.abf.sweepY,medianFilter)
		else:
			self.filteredVm = self.abf.sweepY

		self.filteredDeriv = np.diff(self.filteredVm)

		# scale it to V/S (mV/ms)
		self.filteredDeriv = self.filteredDeriv * self.abf.dataRate / 1000

		# add an initial point so it is the same length as raw data in abf.sweepY
		self.filteredDeriv = np.concatenate(([0],self.filteredDeriv))

		#spikeTimes = _where_cross(sweepDeriv,dVthresholdPos)
		Is=np.where(self.filteredDeriv>dVthresholdPos)[0]
		Is=np.concatenate(([0],Is))
		Ds=Is[:-1]-Is[1:]+1
		spikeTimes0 = Is[np.where(Ds)[0]+1]

		#
		# reduce spike times based on start/stop
		# only include spike times between startPnt and stopPnt
		#print('before stripping len(spikeTimes0):', len(spikeTimes0))
		spikeTimes0 = [spikeTime for spikeTime in spikeTimes0 if (spikeTime>=startPnt and spikeTime<=stopPnt)]
		#print('after stripping len(spikeTimes0):', len(spikeTimes0))

		#
		# if there are doubles, throw-out the second one
		refractory_ms = 10 # remove spike [i] if it occurs within refractory_ms of spike [i-1]
		lastGood = 0 # first spike [0] will always be good, there is no spike [i-1]
		for i in range(len(spikeTimes0)):
			if i==0:
				# first spike is always good
				continue
			dPoints = spikeTimes0[i] - spikeTimes0[lastGood]
			if dPoints < self.abf.dataPointsPerMs*refractory_ms:
				# remove spike time [i]
				spikeTimes0[i] = 0
			else:
				# spike time [i] was good
				lastGood = i
		# regenerate spikeTimes0 by throwing out any spike time that does not pass 'if spikeTime'
		# spikeTimes[i] that were set to 0 above (they were too close to the previous spike)
		# will not pass 'if spikeTime', as 'if 0' evaluates to False
		spikeTimes0 = [spikeTime for spikeTime in spikeTimes0 if spikeTime]

		#
		# todo: make sure all spikes are on upslope

		#
		# for each threshold crossing, search backwards in dV/dt for a % of maximum (about 10 ms)
		dvdt_percentOfMax = 0.1
		window_ms = 2
		window_pnts = window_ms * self.dataPointsPerMs
		spikeTimes1 = []
		for i, spikeTime in enumerate(spikeTimes0):
			# get max in derivative
			preDerivClip = self.filteredDeriv[spikeTime-window_pnts:spikeTime] # backwards
			#preDerivClip = np.flip(preDerivClip)
			peakPnt = np.argmax(preDerivClip)
			peakPnt += spikeTime-window_pnts
			peakVal = self.filteredDeriv[peakPnt]

			# look for % of max
			try:
				percentMaxVal = peakVal * dvdt_percentOfMax # value we are looking for in dv/dt
				preDerivClip = np.flip(preDerivClip) # backwards
				threshPnt2 = np.where(preDerivClip<percentMaxVal)[0][0]
				threshPnt2 = (spikeTime) - threshPnt2
				#print('i:', i, 'spikeTime:', spikeTime, 'peakPnt:', peakPnt, 'threshPnt2:', threshPnt2)
				spikeTimes1.append(threshPnt2)
			except (IndexError) as e:
				print('   error: bAnalysis.spikeDetect0() IndexError spike', i, spikeTime, 'percentMaxVal:', percentMaxVal)
				spikeTimes1.append(spikeTime)

		self.thresholdTimes = spikeTimes0
		self.spikeTimes = spikeTimes1

		return self.spikeTimes, self.thresholdTimes, self.filteredVm, self.filteredDeriv

	def spikeDetect(self, dVthresholdPos=100, medianFilter=0, halfHeights=[20, 50, 80], startSeconds=None, stopSeconds=None):
		'''
		spike detect the current sweep and put results into spikeTime[currentSweep]

		todo: remember values of halfHeights
		'''

		startTime = time.time()

		self.spikeDict = [] # we are filling this in, one entry for each spike

		self.numErrors = 0
		
		# spike detect
		self.spikeTimes, self.thresholdTimes, vm, dvdt = self.spikeDetect0(dVthresholdPos=dVthresholdPos, medianFilter=medianFilter, startSeconds=startSeconds, stopSeconds=stopSeconds)

		#
		# look in a window after each threshold crossing to get AP peak
		# get minima before/after spike
		peakWindow_ms = 10
		peakWindow_pnts = self.abf.dataPointsPerMs * peakWindow_ms
		avgWindow_ms = 5 # we find the min/max before/after (between spikes) and then take an average around this value
		avgWindow_pnts = avgWindow_ms * self.abf.dataPointsPerMs
		avgWindow_pnts = math.floor(avgWindow_pnts/2)
		for i, spikeTime in enumerate(self.spikeTimes):
			# spikeTime units is ALWAYS points
			
			peakPnt = np.argmax(vm[spikeTime:spikeTime+peakWindow_pnts])
			peakPnt += spikeTime
			peakVal = np.max(vm[spikeTime:spikeTime+peakWindow_pnts])

			spikeDict = collections.OrderedDict() # use OrderedDict so Pandas output is in the correct order
			spikeDict['file'] = self.file
			spikeDict['spikeNumber'] = i

			spikeDict['numError'] = 0
			spikeDict['errors'] = []

			# detection params
			spikeDict['dVthreshold'] = dVthresholdPos
			spikeDict['medianFilter'] = medianFilter
			spikeDict['halfHeights'] = halfHeights

			spikeDict['thresholdPnt'] = spikeTime
			spikeDict['thresholdVal'] = vm[spikeTime]
			#spikeDict['thresholdSec'] = (spikeTime / self.abf.dataPointsPerMs) / 1000

			spikeDict['peakPnt'] = peakPnt
			spikeDict['peakVal'] = peakVal
			spikeDict['peakSec'] = (peakPnt / self.abf.dataPointsPerMs) / 1000

			self.spikeDict.append(spikeDict)

			# get pre/post spike minima
			self.spikeDict[i]['preMinPnt'] = None
			self.spikeDict[i]['preMinVal'] = None
			self.spikeDict[i]['postMinPnt'] = None
			self.spikeDict[i]['postMinVal'] = None

			# early diastolic duration
			# 0.1 to 0.5 of time between pre spike min and spike time
			self.spikeDict[i]['preLinearFitPnt0'] = None
			self.spikeDict[i]['preLinearFitPnt1'] = None
			self.spikeDict[i]['earlyDiastolicDuration_ms'] = None # seconds between preLinearFitPnt0 and preLinearFitPnt1
			self.spikeDict[i]['preLinearFitVal0'] = None
			self.spikeDict[i]['preLinearFitVal1'] = None

			self.spikeDict[i]['preSpike_dvdt_max_pnt'] = None
			self.spikeDict[i]['preSpike_dvdt_max_val'] = None # in units mV
			self.spikeDict[i]['preSpike_dvdt_max_val2'] = None # in units dv/dt
			self.spikeDict[i]['postSpike_dvdt_min_pnt'] = None
			self.spikeDict[i]['postSpike_dvdt_min_val'] = None # in units mV
			self.spikeDict[i]['postSpike_dvdt_min_val2'] = None # in units dv/dt

			self.spikeDict[i]['isi_pnts'] = None # time between successive AP thresholds (thresholdSec)
			self.spikeDict[i]['cycleLength_pnts'] = None # time between successive MDPs
			self.spikeDict[i]['cycleLength_ms'] = None # time between successive MDPs

			# Action potential duration (APD) was defined as the interval between the TOP and the subsequent MDP
			self.spikeDict[i]['apDuration_ms'] = None
			self.spikeDict[i]['diastolicDuration_ms'] = None

			if i==0 or i==len(self.spikeTimes)-1:
				continue
			else:
				#
				# pre spike min
				preRange = vm[self.spikeTimes[i-1]:self.spikeTimes[i]]
				preMinPnt = np.argmin(preRange)
				preMinPnt += self.spikeTimes[i-1]
				# the pre min is actually an average around the real minima
				avgRange = vm[preMinPnt-avgWindow_pnts:preMinPnt+avgWindow_pnts]
				preMinVal = np.average(avgRange)

				# search backward from spike to find when vm reaches preMinVal (avg)
				preRange = vm[preMinPnt:self.spikeTimes[i]]
				preRange = np.flip(preRange) # we want to search backwards from peak
				#tmp = np.where(preRange<preMinVal)
				preMinPnt2 = np.where(preRange<preMinVal)[0][0]
				preMinPnt = self.spikeTimes[i] - preMinPnt2

				#
				# linear fit on 10% - 50% of the time from preMinPnt to self.spikeTimes[i]
				startLinearFit = 0.1 # percent of time between pre spike min and AP peak
				stopLinearFit = 0.5 # percent of time between pre spike min and AP peak
				# taking floor() so we always get an integer # points
				timeInterval_pnts = math.floor(self.spikeTimes[i] - preMinPnt)
				preLinearFitPnt0 = preMinPnt + math.floor(timeInterval_pnts * startLinearFit)
				preLinearFitPnt1 = preMinPnt + math.floor(timeInterval_pnts * stopLinearFit)
				preLinearFitVal0 = vm[preLinearFitPnt0]
				preLinearFitVal1 = vm[preLinearFitPnt1]

				#
				# maxima in dv/dt before spike
				preRange = dvdt[self.spikeTimes[i]:peakPnt]
				preSpike_dvdt_max_pnt = np.argmax(preRange)
				preSpike_dvdt_max_pnt += self.spikeTimes[i]
				self.spikeDict[i]['preSpike_dvdt_max_pnt'] = preSpike_dvdt_max_pnt
				self.spikeDict[i]['preSpike_dvdt_max_val'] = vm[preSpike_dvdt_max_pnt] # in units mV
				self.spikeDict[i]['preSpike_dvdt_max_val2'] = dvdt[preSpike_dvdt_max_pnt] # in units mV

				#
				# post spike min
				postRange = vm[self.spikeTimes[i]:self.spikeTimes[i+1]]
				postMinPnt = np.argmin(postRange)
				postMinPnt += self.spikeTimes[i]
				# the post min is actually an average around the real minima
				avgRange = vm[postMinPnt-avgWindow_pnts:postMinPnt+avgWindow_pnts]
				postMinVal = np.average(avgRange)

				# search forward from spike to find when vm reaches postMinVal (avg)
				postRange = vm[self.spikeTimes[i]:postMinPnt]
				try:
					postMinPnt2 = np.where(postRange<postMinVal)[0][0]
					postMinPnt = self.spikeTimes[i] + postMinPnt2
					#print('i:', i, 'postMinPnt:', postMinPnt)
				except (IndexError) as e:
					spikeDict['numError'] = spikeDict['numError'] + 1
					errorStr = 'spike ' + str(i) + ' searching for postMinVal:' + str(postMinVal) + ' postRange min:' + str(np.min(postRange)) + ' max ' + str(np.max(postRange))
					spikeDict['errors'].append(errorStr)
					self.numErrors += 1
					
				#
				# minima in dv/dt after spike
				#postRange = dvdt[self.spikeTimes[i]:postMinPnt]
				postSpike_ms = 10
				postSpike_pnts = self.abf.dataPointsPerMs * postSpike_ms
				#postRange = dvdt[self.spikeTimes[i]:self.spikeTimes[i]+postSpike_pnts] # fixed window after spike
				postRange = dvdt[peakPnt:peakPnt+postSpike_pnts] # fixed window after spike

				'''
				try:
					postSpike_dvdt_min_pnt = np.where(postRange<0)[0][0]
				except:
					print('error: spike', i, 'searhing for post spike min in dv/dt')
				'''
				postSpike_dvdt_min_pnt = np.argmin(postRange)
				#postSpike_dvdt_min_pnt += self.spikeTimes[i]
				postSpike_dvdt_min_pnt += peakPnt
				#print('i:', i, 'postSpike_dvdt_min_pnt:', postSpike_dvdt_min_pnt)
				self.spikeDict[i]['postSpike_dvdt_min_pnt'] = postSpike_dvdt_min_pnt
				self.spikeDict[i]['postSpike_dvdt_min_val'] = vm[postSpike_dvdt_min_pnt]
				self.spikeDict[i]['postSpike_dvdt_min_val2'] = dvdt[postSpike_dvdt_min_pnt]

				self.spikeDict[i]['preMinPnt'] = preMinPnt
				self.spikeDict[i]['preMinVal'] = preMinVal
				self.spikeDict[i]['postMinPnt'] = postMinPnt
				self.spikeDict[i]['postMinVal'] = postMinVal
				# linear fit before spike
				self.spikeDict[i]['preLinearFitPnt0'] = preLinearFitPnt0
				self.spikeDict[i]['preLinearFitPnt1'] = preLinearFitPnt1
				self.spikeDict[i]['earlyDiastolicDuration_ms'] = self.pnt2Ms_(preLinearFitPnt1 - preLinearFitPnt0)
				self.spikeDict[i]['preLinearFitVal0'] = preLinearFitVal0
				self.spikeDict[i]['preLinearFitVal1'] = preLinearFitVal1

				#
				# Action potential duration (APD) was defined as the interval between the TOP and the subsequent MDP
				self.spikeDict[i]['apDuration_ms'] = self.pnt2Ms_(postMinPnt - spikeDict['thresholdPnt'])

				#
				# diastolic duration was defined as the interval between MDP and TOP
				self.spikeDict[i]['diastolicDuration_ms'] = self.pnt2Ms_(spikeTime - preMinPnt)

				self.spikeDict[i]['cycleLength_ms'] = float('nan')
				if i>1:
					self.spikeDict[i]['isi_pnts'] = self.spikeDict[i]['thresholdPnt'] - self.spikeDict[i-1]['thresholdPnt']
					
					cycleLength_pnts = self.spikeDict[i]['postMinPnt'] - self.spikeDict[i-1]['postMinPnt']
					self.spikeDict[i]['cycleLength_pnts'] = cycleLength_pnts
					self.spikeDict[i]['cycleLength_ms'] = self.pnt2Ms_(cycleLength_pnts)

				#
				# get 1/2 height (actually, any number of height measurements)
				# action potential duration using peak and post min
				self.spikeDict[i]['widths'] = []
				for j, halfHeight in enumerate(halfHeights):
					thisVm = postMinVal + (peakVal - postMinVal) * (halfHeight * 0.01)
					#print('halfHeight:', halfHeight, 'thisVm:', thisVm)
					# search from previous min to peak
					'''
					# pre/rising
					preRange = vm[preMinPnt:peakPnt]
					risingPnt = np.where(preRange>thisVm)[0][0] # greater than
					risingPnt += preMinPnt
					risingVal = vm[risingPnt]
					'''
					# post/falling
					#todo: logic is broken, this get over-written in following try
					widthDict = {
						'halfHeight': halfHeight,
						'risingPnt': None,
						'risingVal': None,
						'fallingPnt': None,
						'fallingVal': None,
						'widthPnts': None,
						'widthMs': None
					}
					try:
						postRange = vm[peakPnt:postMinPnt]
						fallingPnt = np.where(postRange<thisVm)[0][0] # less than
						fallingPnt += peakPnt
						fallingVal = vm[fallingPnt]

						# use the post/falling to find pre/rising
						preRange = vm[preMinPnt:peakPnt]
						risingPnt = np.where(preRange>fallingVal)[0][0] # greater than
						risingPnt += preMinPnt
						risingVal = vm[risingPnt]

						# width (pnts)
						widthPnts = fallingPnt - risingPnt
						# assign
						widthDict = {
							'halfHeight': halfHeight,
							'risingPnt': risingPnt,
							'risingVal': risingVal,
							'fallingPnt': fallingPnt,
							'fallingVal': fallingVal,
							'widthPnts': widthPnts,
							'widthMs': widthPnts / self.abf.dataPointsPerMs
						}
					except (IndexError) as e:
						print('error: bAnalysis.spikeDetect() spike', i, 'half height', halfHeight)
						spikeDict[i]['numError'] = spikeDict[i]['numError'] + 1
						errorStr = 'spike ' + str(i) + ' half width ' + str(j)
						spikeDict['errors'].append(errorStr)
						self.numErrors += 1
						#print(e)
					self.spikeDict[i]['widths'].append(widthDict)

		#
		# look between threshold crossing to get minima
		# we will ignore the first and last spike

		#
		# build a list of spike clips
		clipWidth_ms = 500
		clipWidth_pnts = clipWidth_ms * self.abf.dataPointsPerMs
		halfClipWidth_pnts = int(clipWidth_pnts/2)

		# make one x axis clip with the threshold crossing at 0
		self.spikeClips_x = [(x-halfClipWidth_pnts)/self.abf.dataPointsPerMs for x in range(clipWidth_pnts)]

		self.spikeClips = []
		for spikeTime in self.spikeTimes:
			currentClip = vm[spikeTime-halfClipWidth_pnts:spikeTime+halfClipWidth_pnts]
			self.spikeClips.append(currentClip)

		stopTime = time.time()
		print('bAnalysis.spikeDetect() for file', self.file, 'detected', len(self.spikeTimes), 'spikes in', round(stopTime-startTime,2), 'seconds')

	############################################################
	# output reports
	############################################################
	def report(self):
		df = pd.DataFrame(self.spikeDict)
		# limit columns
		#df = df[['file', 'spikeNumber', 'thresholdSec', 'peakSec', 'preMinVal', 'postMinVal', 'widths']]
		return df

	def report2(self):
		newList = []
		for spike in self.spikeDict:
			spikeDict = collections.OrderedDict() # use OrderedDict so Pandas output is in the correct order
			spikeDict['threshold_ms'] = self.pnt2Ms_(spike['thresholdPnt'])
			spikeDict['threshold_mv'] = spike['thresholdVal']
			spikeDict['peak_ms'] = self.pnt2Ms_(spike['peakPnt'])
			spikeDict['peak_mv'] = spike['peakVal']
			spikeDict['preMin_mv'] = spike['preMinVal']
			spikeDict['postMin_mv'] = spike['postMinVal']
			#
			spikeDict['apDuration_ms'] = spike['apDuration_ms']
			spikeDict['earlyDiastolicDuration_ms'] = spike['earlyDiastolicDuration_ms']
			spikeDict['diastolicDuration_ms'] = spike['diastolicDuration_ms']
			#
			if spike['isi_pnts'] is not None:
				spikeDict['isi_ms'] = self.pnt2Ms_(spike['isi_pnts'])
			else:
				spikeDict['isi_ms'] = float('nan')

			spikeDict['cycleLength_ms'] = spike['cycleLength_ms']

			spikeDict['preSpike_dvdt_max_mv'] = spike['preSpike_dvdt_max_val']
			spikeDict['preSpike_dvdt_max_dvdt'] = spike['preSpike_dvdt_max_val2']
			
			spikeDict['postSpike_dvdt_min_mv'] = spike['postSpike_dvdt_min_val']
			spikeDict['postSpike_dvdt_min_dvdt'] = spike['postSpike_dvdt_min_val2']
			
			# half-width
			if 'widths' in spike:
				for widthDict in spike['widths']:
					keyName = 'width_' + str(widthDict['halfHeight'])
					spikeDict[keyName] = widthDict['widthMs']
				
			# errors
			spikeDict['numError'] = spike['numError']
			spikeDict['errors'] = spike['errors']
			

			# append
			newList.append(spikeDict)

		df = pd.DataFrame(newList)
		return df

	#############################
	# utility functions
	#############################
	def pnt2Sec_(self, pnt):
		return pnt / self.abf.dataPointsPerMs / 1000

	def pnt2Ms_(self, pnt):
		return pnt / self.abf.dataPointsPerMs

	def __str__(self):
		retStr = 'file: ' + self.file + '\n' + str(self.abf)
		return retStr

if __name__ == '__main__':
	print('running bAnalysis __main__')
	ba = bAnalysis('../data/19114001.abf')
	print(ba.dataPointsPerMs)