#! /usr/bin/python3 -u
############################################################################################
#
# Weak Signal Map - Rev 1.0
# Copyright (C) 2021 by Joseph B. Attili, aa2il AT arrl DOT net
#
# Gui to plot spots decoded from wsjt over a particular time period.
#
# Notes:
# - Need to install basemap for this to work:
#   sudo apt-get install python3-matplotlib python3-mpltoolkits.basemap
#
############################################################################################
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
############################################################################################

import sys
from PyQt5.QtWidgets import *

from time import sleep
from datetime import timedelta,datetime
from pytz import timezone

from dx.wsjt_helper import *
from dx.cluster_connections import *
from dx.spot_processing import Station, Spot, WWV, Comment, ChallengeData
from pprint import pprint

# JBA - this fixes a bug? in mpl_toolkits
# It appears that basemaps (& python 2.7) are about to become obsolete so
# it is time to start looking for an alternative.
from matplotlib.backends.qt_compat import QtCore, QtWidgets
import matplotlib.pyplot as plt
from matplotlib.figure import Figure

import mpl_toolkits
mpl_toolkits.__path__.append('/usr/lib/python2.7/dist-packages/mpl_toolkits/')
from mpl_toolkits.basemap import Basemap
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

import numpy as np
from itertools import chain
import cProfile
import time 

############################################################################################

BANDS=['160m','80m','40m','30m','20m','17m','15m','12m','10m','6m']
LOGFILE = WSJT_LOGFILE
LOGFILE = WSJT_LOGFILE2

LOGFILE = WSJT_LOGFILE3
LOGFILE = WSJT_LOGFILE4
LOGFILE = WSJT_LOGFILE5

LOGFILE = [WSJT_LOGFILE3,WSJT_LOGFILE4,WSJT_LOGFILE5]
MAX_DAYS=7

############################################################################################

def freq2band(frq_KHz):

    frq = .001*frq_KHz
    if frq<3:
        band=160
    elif frq<5:
        band=80
    elif frq<6:
        band=60
    elif frq<9:
        band=40
    elif frq<12:
        band=30
    elif frq<16:
        band=20
    elif frq<20:
        band=17
    elif frq<23:
        band=15
    elif frq<27:
        band=12
    elif frq<40:
        band=10
    else:
        band=6

    return str(band)+'m'



class WSMAP_GUI(QMainWindow):

    def __init__(self, spots,parent=None):
        super(WSMAP_GUI, self).__init__(parent)

        print('\nInit GUI ...\n')
        self.needed=True
        self.spots=spots
        self.count=0
        self.lines=[]
        self.t1='0000'
        
        # Start by putting up the root window
        self.win  = QWidget()
        self.setCentralWidget(self.win)
        self.setWindowTitle('WS Mapper by AA2IL')

        # We use a simple grid to layout controls
        self.grid = QGridLayout(self.win)
        #self.setLayout(self.grid)
        nrows=6
        ncols=5

        # Create a calendar widget and add it to our layout
        row=0
        col=0
        self.cal = QCalendarWidget()
        self.grid.addWidget(self.cal,row,col,nrows-1,1)
        #self.cal.connect(self.cal, QtCore.SIGNAL('selectionChanged()'), \
        #                 self.date_changed)
        self.cal.clicked.connect(self.date_changed)

        # Don't allow calendar size to change when we resize the window
        sizePolicy = QSizePolicy( QSizePolicy.Fixed,QSizePolicy.Fixed)
        self.cal.setSizePolicy(sizePolicy)

        # The Canvas where we will put the map
        row=1
        col=0
        self.fig = Figure()
        self.canv = FigureCanvas(self.fig)
        #self.grid.addWidget(self.canv,row,col,nrows-row,ncols)
        self.grid.addWidget(self.canv,nrows,col,1,ncols)
        #self.toolbar = NavigationToolbar(self.canvas, self)

        # Allow canvas size to change when we resie the window
        # but make is always visible
        sizePolicy = QSizePolicy( QSizePolicy.MinimumExpanding, 
                                 QSizePolicy.MinimumExpanding)
        self.canv.setSizePolicy(sizePolicy)

        # Draw the map
        self.draw_map()

        # User selections
        row=0
        col=1
        self.dTs = ['1','2','4','8','12','24']
        lb=QLabel("Time Step:")
        self.TimeStep_cb = QComboBox()
        self.TimeStep_cb.addItems(self.dTs)
        self.TimeStep_cb.currentIndexChanged.connect(self.TimeStepSelect)
        self.TimeStepSelect(-1)
        self.grid.addWidget(lb,row+3,col)
        self.grid.addWidget(self.TimeStep_cb,row+3,col+1)

        self.btn1 = QPushButton('<--')
        self.btn1.setToolTip('Click to regress')
        self.btn1.clicked.connect(self.Regress)
        self.grid.addWidget(self.btn1,row+4,col)

        self.btn2 = QPushButton('-->')
        self.btn2.setToolTip('Click to advance')
        self.btn2.clicked.connect(self.Advance)
        self.grid.addWidget(self.btn2,row+4,col+1)

        self.btn3 = QPushButton('All Spots')
        #self.btn3.setToolTip('Showing All Slots')
        self.btn3.clicked.connect(self.needed_only)
        self.grid.addWidget(self.btn3,row+4,col+2)
        self.needed_only(True)

        # Status Boxes
        self.date1a = QLabel()
        self.date1a.setAlignment(QtCore.Qt.AlignCenter)
        self.grid.addWidget(self.date1a,row,col)

        self.date2a = QLabel()
        self.date2a.setAlignment(QtCore.Qt.AlignCenter)
        self.grid.addWidget(self.date2a,row+1,col)

        self.date3a = QLabel()
        self.date3a.setAlignment(QtCore.Qt.AlignCenter)
        self.grid.addWidget(self.date3a,row+2,col)

        self.date1b = QLabel()
        self.date1b.setAlignment(QtCore.Qt.AlignCenter)
        self.grid.addWidget(self.date1b,row,col+1)

        self.date2b = QLabel()
        self.date2b.setAlignment(QtCore.Qt.AlignCenter)
        self.grid.addWidget(self.date2b,row+1,col+1)

        self.date3b = QLabel()
        self.date3b.setAlignment(QtCore.Qt.AlignCenter)
        self.grid.addWidget(self.date3b,row+2,col+1)
        
        self.num_spots = QLabel()
        self.grid.addWidget(self.num_spots,row,ncols-1)

        self.num_dxcc = QLabel()
        self.grid.addWidget(self.num_dxcc,row+1,ncols-1)

        self.num_slots = QLabel()
        self.grid.addWidget(self.num_slots,row+2,ncols-1)

        # Let's roll!
        self.show()
        

    # Function to set time step
    def TimeStepSelect(self,i):
        if i<0:
            self.dT = 24
            idx=self.dTs.index( str(self.dT) )
            self.TimeStep_cb.setCurrentIndex(idx)
        else:
            a=self.dTs[i].split(" ")
            self.dT = int(a[0])


    # Function to toggle needed only slots flag
    def needed_only(self,Init=None):
        if Init:
            self.needed = Init
        else:
            self.needed = not self.needed
            
        if self.needed:
            self.btn3.setText('Needed')
            self.btn3.setToolTip('Showing only Needed Slots')
        else:
            self.btn3.setText('All Slots')
            self.btn3.setToolTip('Showing All Slots')
            
        if not Init:
            self.UpdateMap()

    # Function to advance in time
    def Advance(self):
        print('\nAdvance:',self.dT)
        print(self.date1,self.date2)
        self.date1 += timedelta(hours=self.dT)
        self.date2 = self.date1 + timedelta(hours=self.dT)
        print(self.date1,self.date2)

        self.t1 = '%2.2d00' % self.date1.hour
        print('t1=',self.t1,self.date1.hour,self.date1.minute,)

        self.UpdateMap()

        
    # Function to regress in time
    def Regress(self):
        print('\nRegress:',self.dT)
        print(self.date1,self.date2)
        self.date1 -= timedelta(hours=self.dT)
        self.date2 = self.date1 + timedelta(hours=self.dT)
        print(self.date1,self.date2)

        self.t1 = '%2.2d00' % self.date1.hour
        print('t1=',self.t1,self.date1.hour,self.date1.minute,)
        
        self.UpdateMap()

        
    # Handler called when the date selection has changed
    def date_changed(self):

        print('Date Changed:')

        # Fetch the currently selected date, this is a QDate object
        date = self.cal.selectedDate()
        date0 = date.toPyDate()
        
        self.date1 = datetime.strptime( date0.strftime("%Y%m%d")+' '+self.t1, "%Y%m%d %H%M") 
        #.replace(tzinfo=pytz.utc)
        self.date2 = self.date1 + timedelta(hours=self.dT)
        
        print('t1=',self.t1)
        print('date=',date)
        print('date0=',date0)
        print('date1=',self.date1)
        print('date2=',self.date2)
        
        self.UpdateMap()
        
    # Function to print summary of spot list
    def print_summary(self,spots):

        if False:
            #print spots2
            for i in range(len(spots2)):
                #print spots2[i]
                print(spots2[i]['date'],spots2[i]['time'],spots2[i]['band'],\
                    '\t',spots2[i]['call2'],'\t',spots2[i]['country'],\
                    '\t',spots2[i]['snr'])

        calls = list(set( [x['call2'] for x in spots] ))
        #print ' ' #calls
        for call in calls:
            dx = Station(call)
            snrs = [x['snr'] for x in spots if x['call2']==call]
            #print '{0: <8}'.format(call),':','{0: <10}'.format(dx.country),':',snrs
            print('{:8.8} : {:15.15} :'.format(call,dx.country),snrs)

            

    # Function to draw spots on the map
    def UpdateMap(self):
        
        # Update Gui
        fmt = "%m/%d %H:%M %Z"
        date1 = pytz.utc.localize( self.date1 )
        date2 = pytz.utc.localize( self.date2 )
        self.date1a.setText( date1.strftime(fmt) )
        self.date2a.setText( date2.strftime(fmt) )
        self.date1b.setText( date1.astimezone(timezone('US/Pacific')).strftime(fmt) )
        self.date2b.setText( date2.astimezone(timezone('US/Pacific')).strftime(fmt) )
        now_utc = datetime.now(timezone('UTC'))
        self.date3a.setText( now_utc.strftime(fmt) )
        self.date3b.setText( now_utc.astimezone(timezone('US/Pacific')).strftime(fmt) )

        self.cal.setSelectedDate(date1)

        # Clear the current spots
        self.count+=1
        if self.count>1:
            print('Clearing canvas...',self.count)
            for i in range(len(BANDS)):
                self.lines[i].remove()
            self.canv.draw()
            print('... Canvas cleared.')

        # Shade the night areas
        if self.count>1:
            for item in self.CS.collections:
                item.remove()
        self.CS=self.m.nightshade(self.date1,alpha=0.2)

        # make size of markers proportional to SNR
        ymax = 100.
        ymin = 5.
        xmax = 0.
        xmin = -20.
        slope = (ymax - ymin) / (xmax-xmin)
        offset = ymin - slope*xmin

        # Loop over all the bands
        #colors=['r','g','b','k','m','y','c','r','g','b','k','m','y','c']
        colors=['lime','magenta','blue','green','salmon','yellow',\
                'orange','brown','purple','red']
        spots2 = filter_spots(self.spots,self.date1,self.date2,Need=self.needed)
        dxccs = count_dxccs(spots2)
        print('dxccs=',dxccs)
        self.num_spots.setText( ('%d Spots' % len(spots2)) )
        self.num_dxcc.setText( ('%d DXCCs' % len(dxccs)) )

        nslots = 0
        for i in range(len(BANDS)):
            spots3 = filter_spots(spots2,band=BANDS[i])
            nslots += len( count_dxccs(spots3) )
            self.num_slots.setText( ('%d Slots' % nslots) )
            if self.needed:
                self.print_summary(spots3)

            lats = [x['lat'] for x in spots3]
            lons = [x['lon'] for x in spots3]
            size  = [slope*s['snr']+offset for s in spots3]

            if False:
                # These corrections are needed if/when we use the miller projection in basemap
                for j in range(len(lats)):
                    if lats[j] is None:
                        lats[j]=0.
                        size[j]=1
                    else:
                        lats[j]=float(lats[j])
                    if lons[j] is None:
                        lons[j]=0.
                        size[j]=1
                    else:
                        lons[j]=float(lons[j])

                #print lats
                #print lons

            x, y = self.m(lons,lats)

            if True:
                line = self.m.scatter(x,y,marker='o', c=colors[i], edgecolors=colors[i],\
                                      s=size,alpha=0.3, \
                                      label=BANDS[i])
            else:
                line = self.m.scatter(lons,lats,latlon=True,
                                      marker='o', c=colors[i], 
                                      s=size,alpha=0.3, 
                                      label=BANDS[i])
            if self.count==1:
                self.lines.append(line)
            else:
                self.lines[i]=line

        # refresh canvas
        self.canv.draw()
                
        if self.count==1:
            self.ax.legend(loc='lower center',fontsize='small',\
                           ncol=len(self.lines),scatterpoints=1)




    
    # Draw a shaded-relief image
    def draw_map(self,scale=0.01):
        self.ax = self.fig.add_subplot(111)
        self.fig.tight_layout(pad=0)

        lon_offset=30
        if True:
            m = Basemap(projection='cyl', resolution='c',
                        llcrnrlat=-90, urcrnrlat=90,
                        llcrnrlon=-180, urcrnrlon=180,
                        fix_aspect=False, ax=self.ax)
            m.shadedrelief(scale=scale)
            #m.bluemarble(scale=scale)
            #m.etopo(scale=scale)
        elif Fale:
            # Great circle map - sort of works but grey line is hosed up
            lon_0 = -105; lat_0 = 40
            m = Basemap(projection='aeqd',lat_0=lat_0,lon_0=lon_0,
                        fix_aspect=False, ax=self.ax)
            # fill background.
            m.drawmapboundary(fill_color='aqua')
            # draw coasts and fill continents.
            m.drawcoastlines(linewidth=0.5)
            m.fillcontinents(color='coral',lake_color='aqua')
            # 20 degree graticule.
            #m.drawparallels(np.arange(-80,81,20))
            #m.drawmeridians(np.arange(-180,180,20))
            # draw a black dot at the center.
            xpt, ypt = m(lon_0, lat_0)
            m.plot([xpt],[ypt],'ko')
            self.m = m
            return
        elif False:
            # There is a bug in basemap that prevents the reset of these from working
            # Need to update at some point - seems like a pain though
            # Search on     matplotlib basemap error in warpimage   to see error
            m = Basemap(projection='mill', resolution='c',
                        lon_0=-90,
                        fix_aspect=False, ax=self.ax)
            m.shadedrelief(scale=scale)
        elif False:
            m = Basemap(projection='cyl', resolution='c',
                        lon_0=-90,lat_0=0,
                        fix_aspect=False, ax=self.ax)
        elif False:
            m = Basemap(projection='cass', resolution='c',
                        llcrnrlat=-80, urcrnrlat=80,
                        llcrnrlon=-180, urcrnrlon=180,
                        lon_0=30.,lat_0=10.,
                        fix_aspect=False, ax=self.ax)
        else:
            m = Basemap(projection='eck4', resolution='c',
                        lon_0=30.,
                        fix_aspect=False, ax=self.ax)
        self.m = m
    
        # lats and longs are returned as a dictionary
        lats = m.drawparallels(np.linspace(-90, 90, 13))
        lons = m.drawmeridians(np.linspace(-180, 180, 13))
    
        # keys contain the plt.Line2D instances
        lat_lines = chain(*(tup[1][0] for tup in lats.items()))
        lon_lines = chain(*(tup[1][0] for tup in lons.items()))
        all_lines = chain(lat_lines, lon_lines)
    
        # cycle through these lines and set the desired style
        for line in all_lines:
            line.set(linestyle='-', alpha=0.3, color='w')

        # Draw politcal boundaries
        m.drawcoastlines()
        m.drawstates()
        m.drawcountries()

        # discards the old graph
        #ax.clear()

        # plot data
        #ax.plot(data, '*-')

        # refresh canvas
        #self.canvas.draw()



def load_spots():
    
    rootlogger = "dxcsucker"
    logger = get_logger(rootlogger)

    if False:
    #if True:
        print('Reading spot data ...')
        fp = open('spots.pcl','rb')
        spots = pickle.load( fp )
        fp.close()
        print('... Read spot data.')
        return spots

    tn = wsjt_helper(LOGFILE,MAX_DAYS)
    spots=tn.read_all_spots(MAX_DAYS)
    print('size=',sys.getsizeof(spots))
    print('size=',sys.getsizeof(spots[0]))

    print('Filling out spot data ...',len(spots))
    fp1 = open('needed.csv', 'w')
    for i in range(len(spots)):
        call = spots[i]['call2']
        dx = Station(call)
        band = freq2band(spots[i]['freq'])
        dx.needed = chdata.needed_challenge(dx.country,band.upper(),0)
        
        if i==0 and False:
            print('Spot 0=',spots[i])
            print('dx=',pprint(vars(dx)))
        if i%100000 ==0:
            print('i=',i,'\tlen=',len(spots))
        if call=='OH8JK':
            print('HEY:',spots[i])
 
        spots[i]['country'] = dx.country
        spots[i]['lat'] = dx.latitude
        lon = dx.longitude
        if lon:
            spots[i]['lon'] = -lon
        else:
            spots[i]['lon'] = lon             # None
        spots[i]['band'] = band
        spots[i]['Needed'] = dx.needed
        #spots[i]['TimeStamp'] = datetime.strptime( spots[i]['date']+' '+spots[i]['time'],
        #"%Y-%m-%d %H%M%S") 

        if i==0:
            print(spots[i])
            print('size=',sys.getsizeof(spots))
            print('size=',sys.getsizeof(spots[0]),sys.getsizeof(dx))

        if dx.needed:
            fp1.write('%s,%s,%s,%s,%s,%s\n' % \
                      ( spots[i]['date'], spots[i]['time'],   spots[i]['band'],\
                        spots[i]['call2'],spots[i]['country'],spots[i]['snr'] ) )
            fp1.flush()

    if len(spots)>0:
        #print 'First spot:',spots[0]
        #print 'Last  spot:',spots[-1]
        pass
    else:
        print('No spots loaded')

    #print( '-%s- -%s-\n',(date,spots[-1]['date']) )

    if False:
        print('Saving spot data...')
        fp = open('spots.pcl','wb')
        pickle.dump( spots,fp )
        fp.close()
        print('... Saved spot data.')

    return spots


def count_dxccs(spots):
    dxccs = list(set( [x['country'] for x in spots] ))
    return dxccs
    

def filter_spots(spots,date1=[],date2=[],band=[],Need=False):
    
    print('\nSelecting spots ...',date1,date2,band,Need)
    if len(band)==0:
        date1 = date1.replace(tzinfo=pytz.utc)
        date2 = date2.replace(tzinfo=pytz.utc)
        spots2 =[x for x in spots if x["TimeStamp"] >= date1 and \
                 x["TimeStamp"] < date2 and (not Need or x['Needed']) ]
    elif len(date1)==0 and len(date2)==0:
        spots2 =[x for x in spots if x['band']==band and \
                 (not Need or x['Needed']) ]
    else:
        date1 = date1.replace(tzinfo=pytz.utc)
        date2 = date2.replace(tzinfo=pytz.utc)
        spots2 =[x for x in spots if x["TimeStamp"] >= date1 and \
                 x["TimeStamp"] < date2 and x['band']==band and \
                 (not Need or x['Needed']) ]

    return spots2


############################################################################################

# If the program is run directly or passed as an argument to the python
# interpreter then create a Calendar instance and show it
if __name__ == "__main__":

    if False:
        date = datetime.utcnow()
        print(' ')
        print(date)
        print(date1)
        sys.exit(0)
        
        fmt = "%Y-%m-%d %H:%M:%S %Z%z"
        now_utc = datetime.now(timezone('UTC'))
        print(now_utc.strftime(fmt))

        now_pacific = now_utc.astimezone(timezone('US/Pacific'))
        print(now_pacific.strftime(fmt))
        sys.exit(0)

        naive = datetime.now()
        pst_now = pytz.timezone('US/Pacific').localize(naive)
        print(naive)
        print(naive.tzinfo)

        print(pst_now)
        utc_now = pytz.utc.localize(datetime.utcnow())
        pst_now = utc_now.astimezone(pytz.timezone("America/Los_Angeles"))
        print(utc_now)
        print(pst_now)
        sys.exit(0)

    print('\n****************************************************************************')
    print('\n   WS Mapper beginning ...\n')

    pr = cProfile.Profile()
    chdata = ChallengeData('/home/joea/AA2IL/states.xls')
    
    pr.enable()
    spots  = load_spots()
    pr.disable()
    pr.print_stats(sort='time')
    #sys.exit(0)
    
    app  = QApplication(sys.argv)
    gui  = WSMAP_GUI(spots)
    
    date = gui.date_changed()
 
    sys.exit(app.exec_())
    
