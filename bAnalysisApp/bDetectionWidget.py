import sys
from functools import partial

from PyQt5 import QtCore, QtWidgets, QtGui
import pyqtgraph as pg


class bDetectionWidget(QtWidgets.QWidget):
	def __init__(self, ba, parent=None):
		"""
		ba: bAnalysis object
		"""
		
		super(bDetectionWidget, self).__init__(parent)

		self.ba = ba
		
		self.myPlotList = []

		# a list of possible x/y plots
		self.myPlots = [
			{
				'humanName': 'Threshold Sec (dV/dt)',
				'x': 'thresholdSec',
				'y': 'thresholdVal_dvdt',
				'convertx_tosec': False, # some stats are in points, we need to convert to seconds
				'color': 'r',
				'symbol': 'o',
				'plotOn': 'dvdt', # which plot to overlay (vm, dvdt)
				'plotIsOn': False,
			},
			{
				'humanName': 'Peak Sec (Vm)',
				'x': 'peakSec',
				'y': 'peakVal',
				'convertx_tosec': False,
				'color': 'r',
				'symbol': 'o',
				'plotOn': 'vm',
				'plotIsOn': False,
			},
			{
				'humanName': 'Pre Min (Vm)',
				'x': 'preMinPnt',
				'y': 'preMinVal',
				'convertx_tosec': True,
				'color': 'g',
				'symbol': 'o',
				'plotOn': 'vm',
				'plotIsOn': False,
			},
			{
				'humanName': 'Post Min (Vm)',
				'x': 'postMinPnt',
				'y': 'postMinVal',
				'convertx_tosec': True,
				'color': 'b',
				'symbol': 'o',
				'plotOn': 'vm',
				'plotIsOn': False,
			},
		]
		
		self.buildUI()
		
	'''
	def _toggle_plot(self, idx, on):
		if on:
			pass
		else:
			self.myPlotList[idx].setData(x=[], y=[])
	'''
			
	def set_ba(self, ba):
		"""
		set self.ba to new bAnalysis object ba
		"""
		self.ba = ba
		
		### REPLOT ###
		self.replot()
		
	def on_scatterClicked(self, scatter, points):
		print('scatterClicked() scatter:', scatter, points)

	def togglePlot(self, idx, on):
		"""
		Toggle overlay of stats like spike peak.
		
		idx: overlay index into self.myPlots
		on: boolean
		"""
		
		print('togglePlot()', idx, on)
		
		# toggle the plot on/off
		self.myPlots[idx]['plotIsOn'] = on
		
		#We do not want to setData as it seems to trash x/y data if it is not specified
		#We just want to set the pen/size in order to show/hide
		plot = self.myPlots[idx]
		if on:
			#self.myPlotList[idx].setData(pen=pg.mkPen(width=5, color=plot['color'], symbol=plot['symbol']), size=2)
			self.myPlotList[idx].setPen(pg.mkPen(width=5, color=plot['color'], symbol=plot['symbol']))
			self.myPlotList[idx].setSize(2)
		else:
			#self.myPlotList[idx].setData(pen=pg.mkPen(width=0, color=plot['color'], symbol=plot['symbol']), size=0)
			self.myPlotList[idx].setPen(pg.mkPen(width=0, color=plot['color'], symbol=plot['symbol']))
			self.myPlotList[idx].setSize(0)

	def replot(self):

		for idx, plot in enumerate(self.myPlots):
			xPlot, yPlot = self.ba.getStat(plot['x'], plot['y'])
			if plot['convertx_tosec']:
				xPlot = [self.ba.pnt2Sec_(x) for x in xPlot] # convert pnt to sec

			self.myPlotList[idx].setData(x=xPlot, y=yPlot)
			
			self.togglePlot(idx, plot['plotIsOn'])
			
	
	def buildUI(self):
		self.myHBoxLayout_detect = QtWidgets.QHBoxLayout(self)

		# detection widget toolbar
		detectToolbarWidget = myDetectToolbarWidget(self.myPlots, self)
		self.myHBoxLayout_detect.addLayout(detectToolbarWidget) # stretch=10, not sure on the units???
		
		print('bDetectionWidget.buildUI() building pg.GraphicsLayoutWidget')
		self.view = pg.GraphicsLayoutWidget()
		self.view.show()
		self.derivPlot = self.view.addPlot(row=0, col=0)
		self.vmPlot = self.view.addPlot(row=1, col=0)

		# link x-axis of deriv and vm
		self.derivPlot.setXLink(self.vmPlot)
		self.vmPlot.setXLink(self.derivPlot)
		
		# turn off x/y dragging of deriv and vm
		self.derivPlot.setMouseEnabled(x=False, y=False)
		self.vmPlot.setMouseEnabled(x=False, y=False)
		
		print('bDetectionWidget.buildUI() building lines for deriv')
		lines = MultiLine(self.ba.abf.sweepX, self.ba.filteredDeriv)
		self.derivPlot.addItem(lines)

		print('bDetectionWidget.buildUI() building lines for vm')
		lines = MultiLine(self.ba.abf.sweepX, self.ba.abf.sweepY)
		self.vmPlot.addItem(lines)

		
		# add all plots
		self.myPlotList = [] # list of pg.ScatterPlotItem
		for idx, plot in enumerate(self.myPlots):
			color = plot['color']
			symbol = plot['symbol']			
			myScatterPlot = pg.ScatterPlotItem(pen=pg.mkPen(width=5, color=color), symbol=symbol, size=2)
			myScatterPlot.setData(x=[], y=[]) # start empty
			myScatterPlot.sigClicked.connect(self.on_scatterClicked)
		
			self.myPlotList.append(myScatterPlot)

			# add plot to pyqtgraph
			if plot['plotOn'] == 'vm':
				self.vmPlot.addItem(myScatterPlot)
			elif plot['plotOn'] == 'dvdt':
				self.derivPlot.addItem(myScatterPlot)

		self.replot()
		
		#
		print('bDetectionWidget.buildUI() adding view to myQVBoxLayout')
		self.myHBoxLayout_detect.addWidget(self.view) # stretch=10, not sure on the units???

		print('bDetectionWidget.buildUI() done')
		
class MultiLine(pg.QtGui.QGraphicsPathItem):
	"""
	This will display a time-series whole-cell recording efficiently
	It does this by converting the array of points to a QPath
	"""
	def __init__(self, x, y):
		"""x and y are 2D arrays of shape (Nplots, Nsamples)"""
		
		self.xStart = None
		self.xCurrent = None
		self.linearRegionItem = None

		self.path = pg.arrayToQPath(x.flatten(), y.flatten(), connect='all')
		pg.QtGui.QGraphicsPathItem.__init__(self, self.path)

		# holy shit, this is bad, without this the app becomes non responsive???
		# if width > 1.0 then this whole app STALLS
		self.setPen(pg.mkPen(color='k', width=1))
	def shape(self):
		# override because QGraphicsPathItem.shape is too expensive.
		#print(time.time(), 'MultiLine.shape()', pg.QtGui.QGraphicsItem.shape(self))
		return pg.QtGui.QGraphicsItem.shape(self)
	def boundingRect(self):
		#print(time.time(), 'MultiLine.boundingRect()', self.path.boundingRect())
		return self.path.boundingRect()

	def mouseDragEvent(self, ev):
		#print('myGraphicsLayoutWidget.mouseDragEvent(self, ev):')

		if ev.button() != QtCore.Qt.LeftButton:
			ev.ignore()
			return

		if ev.isStart():
			self.xStart = ev.buttonDownPos()[0]
			self.linearRegionItem = pg.LinearRegionItem(values=(self.xStart,0), orientation=pg.LinearRegionItem.Vertical)
			#self.linearRegionItem.sigRegionChangeFinished.connect(self.update_x_axis)
			# add the LinearRegionItem to the parent widget (Cannot add to self as it is an item)
			self.parentWidget().addItem(self.linearRegionItem)
		elif ev.isFinish():
			self.parentWidget().setXRange(self.xStart, self.xCurrent)

			self.xStart = None
			self.xCurrent = None
			
			self.parentWidget().removeItem(self.linearRegionItem)
			self.linearRegionItem = None
			
			
			return
		
		self.xCurrent = ev.pos()[0]
		#print('xStart:', self.xStart, 'self.xCurrent:', self.xCurrent)
		self.linearRegionItem.setRegion((self.xStart, self.xCurrent))
		ev.accept()
		
	'''
	def update_x_axis(self):
		print('myGraphicsLayoutWidget.update_x_axis()')
	'''
	
	'''
	def mouseClickEvent(self, ev):
		print('myGraphicsLayoutWidget.mouseClickEvent(self, ev):')
	'''

#class myDetectToolbarWidget(QtWidgets.QToolBar):
class myDetectToolbarWidget(QtWidgets.QVBoxLayout):
	def __init__(self, myPlots, detectionWidget, parent=None):
		"""
		myPlots is a list of dict describing each x/y plot (on top of vm and/or dvdt)
		"""
		
		super(myDetectToolbarWidget, self).__init__(parent)

		self.detectionWidget = detectionWidget
		
		buttonName = 'Detect'
		button = QtWidgets.QPushButton(buttonName)
		button.setToolTip('Detect Spikes')
		button.clicked.connect(partial(self.on_button_click,buttonName))
		self.addWidget(button)

		self.dvdtThreshold = QtWidgets.QDoubleSpinBox()
		self.dvdtThreshold.setMinimum(-1e6)
		self.dvdtThreshold.setMaximum(+1e6)
		self.dvdtThreshold.setValue(50)
		self.addWidget(self.dvdtThreshold)
		
		self.minSpikeVm = QtWidgets.QDoubleSpinBox()
		self.minSpikeVm.setMinimum(-1e6)
		self.minSpikeVm.setMaximum(+1e6)
		self.minSpikeVm.setValue(-20)
		self.addWidget(self.minSpikeVm)
		
		for idx, plot in enumerate(myPlots):
			humanName = plot['humanName']
			checkbox = QtWidgets.QCheckBox(plot['humanName'])
			checkbox.setChecked(False)
			#checkbox.stateChanged.connect(lambda:self.on_check_click(checkbox))
			checkbox.stateChanged.connect(partial(self.on_check_click,checkbox,idx))
			self.addWidget(checkbox)
			
	def on_check_click(self, checkbox, idx):
		print('on_check_click()', checkbox.text(), checkbox.isChecked(), idx)
		self.detectionWidget.togglePlot(idx, checkbox.isChecked())
		
	@QtCore.pyqtSlot()
	def on_button_click(self, name):
		print('=== myDetectToolbarWidget.on_button_click() name:', name)
		dvdtValue = self.dvdtThreshold.value()
		minSpikeVm = self.minSpikeVm.value()
		print('    dvdtValue:', dvdtValue)
		print('    minSpikeVm:', minSpikeVm)
		self.detectionWidget.ba.spikeDetect(dVthresholdPos=dvdtValue, minSpikeVm=minSpikeVm)
		
		self.detectionWidget.replot()
		
if __name__ == '__main__':
	# load a bAnalysis file
	from bAnalysis import bAnalysis

	abfFile = '/Users/cudmore/Sites/bAnalysis/data/19221021.abf'
	abfFile = '/Users/cudmore/Sites/bAnalysis/data/19114001.abf'
	ba = bAnalysis(file=abfFile)

	# spike detect
	ba.getDerivative(medianFilter=5) # derivative
	ba.spikeDetect(dVthresholdPos=50, minSpikeVm=-20, medianFilter=0)

	pg.setConfigOption('background', 'w')
	pg.setConfigOption('foreground', 'k')

	app = QtWidgets.QApplication(sys.argv)
	w = bDetectionWidget(ba)
	w.show()

	sys.exit(app.exec_())
