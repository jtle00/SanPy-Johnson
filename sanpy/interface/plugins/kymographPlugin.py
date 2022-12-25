from sanpy.sanpyLogger import get_logger
logger = get_logger(__name__)

import sanpy
from sanpy.interface.plugins import sanpyPlugin
#from sanpy.interface import kymographWidget

class kymographPlugin(sanpyPlugin):
    myHumanName = 'Kymograph'

    #def __init__(self, myAnalysisDir=None, **kwargs):
    def __init__(self, plotRawAxis=False, ba=None, **kwargs):
        """
        Args:
            ba (bAnalysis): Not required
        """
        
        logger.info('')
        
        super().__init__(ba=ba, **kwargs)

        # don't create until we get a good ba
        # if ba is None:
        #     self._kymWidget = None
        # else:
        #     self._kymWidget = sanpy.interface.kymographPlugin2(ba)
        self._kymWidget = sanpy.interface.kymographPlugin2(ba)

    def getWidget(self):
        return self._kymWidget

    def replot(self):
        #path = self.ba.getFilePath()
        if self._kymWidget is None:
            self._kymWidget = sanpy.interface.kymographPlugin2(self.ba)
        self._kymWidget.slotSwitchFile(self.ba)

    def slot_switchFile(self, rowDict, ba, replot=True):
        # don't replot until we set our detectionClass
        replot = False
        super().slot_switchFile(rowDict, ba, replot=replot)

        if ba is not None and ba.myFileType != 'tif':
            logger.error(f'only tif files are supported')
            #self._initError = True
            return

        self.replot()

    def getWidget(self):
        """Over-ride if plugin makes its own widget.
        """
        return self._kymWidget

