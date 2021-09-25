import numpy as np
import scipy.signal

from PyQt5 import QtCore, QtWidgets, QtGui

import matplotlib.pyplot as plt

from sanpy.sanpyLogger import get_logger
logger = get_logger(__name__)

import sanpy
from sanpy.interface.plugins import sanpyPlugin

from sanpy.bAnalysisUtil import statList

class exportTrace(sanpyPlugin):
	"""
	"""
	myHumanName = 'Export Trace'

	def __init__(self, **kwargs):
		super(exportTrace, self).__init__(**kwargs)

		# this plugin will not respond to any interface changes
		self.turnOffAllSignalSlot()

		self.plot()

	def plot(self):
		if self.ba is None:
			return

		self.myType = 'vmFiltered'

		if self.myType == 'vmFiltered':
			xyUnits = ('Time (sec)', 'Vm (mV)')# todo: pass xMin,xMax to constructor
			x = self.getSweep('x')  # self.ba.sweepX()
			y = self.getSweep('y')  # self.ba.sweepY()
		elif self.myType == 'dvdtFiltered':
			xyUnits = ('Time (sec)', 'dV/dt (mV/ms)')# todo: pass xMin,xMax to constructor
		elif self.myType == 'meanclip':
			xyUnits = ('Time (ms)', 'Vm (mV)')# todo: pass xMin,xMax to constructor
		else:
			logger.error(f'Unknown myType: "{self.myType}"')
			xyUnits = ('error time', 'error y')

		path = self.ba.path

		xMin, xMax = self.getStartStop()
		'''
		xMin = None
		xMax = None
		if self.myType in ['clip', 'meanclip']:
			xMin, xMax = self.detectionWidget.clipPlot.getAxis('bottom').range
		else:
			xMin, xMax = self.detectionWidget.getXRange()
		'''

		if self.myType in ['vm', 'dvdt']:
			xMargin = 2 # seconds
		else:
			xMargin = 2

		tmpLayout = QtWidgets.QVBoxLayout()

		self.mainWidget = sanpy.interface.bExportWidget(x, y,
						xyUnits=xyUnits,
						path=path,
						xMin=xMin, xMax=xMax,
						xMargin = xMargin,
						type = self.myType,
						darkTheme = True)
						#darkTheme=self.detectionWidget.useDarkStyle)

		tmpLayout.addWidget(self.mainWidget)

		# rewire existing widget into plugin architecture
		#self.mainWidget.closeEvent = self.onClose
		self._mySetWindowTitle()

		#self.setCentralWidget(self.mainWidget)
		self.setLayout(tmpLayout)

if __name__ == '__main__':
	path = '/home/cudmore/Sites/SanPy/data/19114001.abf'
	ba = sanpy.bAnalysis(path)
	ba.spikeDetect()
	print(ba.numSpikes)

	import sys
	app = QtWidgets.QApplication([])
	et = exportTrace(ba=ba)
	et.show()
	sys.exit(app.exec_())
