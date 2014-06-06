# emacs: -*- mode: python; py-indent-offset: 4; indent-tabs-mode: t -*-
# vi: set ft=python sts=4 ts=4 sw=4 noet :

# This file is part of Fail2Ban.
#
# Fail2Ban is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# Fail2Ban is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Fail2Ban; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# Author: Serg G. Brester (sebres)
# 

__author__ = "Serg G. Brester (sebres)"
__copyright__ = "Copyright (c) 2014 Serg G. Brester"
__license__ = "GPL"

import os
import sys
import unittest
import tempfile
import time

from ..server.mytime import MyTime
from ..server.ticket import FailTicket
from ..server.observer import Observers, ObserverThread
from .utils import LogCaptureTestCase
from .dummyjail import DummyJail
try:
	from ..server.database import Fail2BanDb
except ImportError:
	Fail2BanDb = None


class BanTimeIncr(LogCaptureTestCase):

	def setUp(self):
		"""Call before every test case."""
		super(BanTimeIncr, self).setUp()
		self.__jail = DummyJail()
		self.__jail.calcBanTime = self.calcBanTime
		self.Observer = ObserverThread()

	def tearDown(self):
		super(BanTimeIncr, self).tearDown()

	def calcBanTime(self, banTime, banCount):
		return self.Observer.calcBanTime(self.__jail, banTime, banCount)

	def testDefault(self, multipliers = None):
		a = self.__jail;
		a.setBanTimeExtra('increment', 'true')
		a.setBanTimeExtra('maxtime', '1d')
		a.setBanTimeExtra('rndtime', None)
		a.setBanTimeExtra('factor', None)
		# tests formulat or multipliers:
		a.setBanTimeExtra('multipliers', multipliers)
		# test algorithm and max time 24 hours :
		self.assertEqual(
			[a.calcBanTime(600, i) for i in xrange(1, 11)],
			[1200, 2400, 4800, 9600, 19200, 38400, 76800, 86400, 86400, 86400]
		)
		# with extra large max time (30 days):
		a.setBanTimeExtra('maxtime', '30d')
		# using formula the ban time grows always, but using multipliers the growing will stops with last one:
		arr = [1200, 2400, 4800, 9600, 19200, 38400, 76800, 153600, 307200, 614400]
		if multipliers is not None:
			multcnt = len(multipliers.split(' '))
			if multcnt < 11:
				arr = arr[0:multcnt-1] + ([arr[multcnt-2]] * (11-multcnt))
		self.assertEqual(
			[a.calcBanTime(600, i) for i in xrange(1, 11)],
		  arr
		)
		a.setBanTimeExtra('maxtime', '1d')
		# change factor :
		a.setBanTimeExtra('factor', '2');
		self.assertEqual(
			[a.calcBanTime(600, i) for i in xrange(1, 11)],
			[2400, 4800, 9600, 19200, 38400, 76800, 86400, 86400, 86400, 86400]
		)
		# factor is float :
		a.setBanTimeExtra('factor', '1.33');
		self.assertEqual(
			[int(a.calcBanTime(600, i)) for i in xrange(1, 11)],
			[1596, 3192, 6384, 12768, 25536, 51072, 86400, 86400, 86400, 86400]
		)
		a.setBanTimeExtra('factor', None);
		# change max time :
		a.setBanTimeExtra('maxtime', '12h')
		self.assertEqual(
			[a.calcBanTime(600, i) for i in xrange(1, 11)],
			[1200, 2400, 4800, 9600, 19200, 38400, 43200, 43200, 43200, 43200]
		)
		a.setBanTimeExtra('maxtime', '24h')
		## test randomization - not possibe all 10 times we have random = 0:
		a.setBanTimeExtra('rndtime', '5m')
		self.assertTrue(
			False in [1200 in [a.calcBanTime(600, 1) for i in xrange(10)] for c in xrange(10)]
		)
		a.setBanTimeExtra('rndtime', None)
		self.assertFalse(
			False in [1200 in [a.calcBanTime(600, 1) for i in xrange(10)] for c in xrange(10)]
		)
		# restore default:
		a.setBanTimeExtra('multipliers', None)
		a.setBanTimeExtra('factor', None);
		a.setBanTimeExtra('maxtime', '24h')
		a.setBanTimeExtra('rndtime', None)

	def testMultipliers(self):
		# this multipliers has the same values as default formula, we test stop growing after count 9:
		self.testDefault('1 2 4 8 16 32 64 128 256')
		# this multipliers has exactly the same values as default formula, test endless growing (stops by count 31 only):
		self.testDefault(' '.join([str(1<<i) for i in xrange(31)]))

	def testFormula(self):
		a = self.__jail;
		a.setBanTimeExtra('maxtime', '24h')
		a.setBanTimeExtra('rndtime', None)
		## use another formula:
		a.setBanTimeExtra('formula', 'ban.Time * math.exp(float(ban.Count+1)*banFactor)/math.exp(1*banFactor)')
		a.setBanTimeExtra('factor', '2.0 / 2.885385')
		a.setBanTimeExtra('multipliers', None)
		# test algorithm and max time 24 hours :
		self.assertEqual(
			[int(a.calcBanTime(600, i)) for i in xrange(1, 11)],
			[1200, 2400, 4800, 9600, 19200, 38400, 76800, 86400, 86400, 86400]
		)
		# with extra large max time (30 days):
		a.setBanTimeExtra('maxtime', '30d')
		self.assertEqual(
			[int(a.calcBanTime(600, i)) for i in xrange(1, 11)],
			[1200, 2400, 4800, 9600, 19200, 38400, 76800, 153601, 307203, 614407]
		)
		a.setBanTimeExtra('maxtime', '24h')
		# change factor :
		a.setBanTimeExtra('factor', '1');
		self.assertEqual(
			[int(a.calcBanTime(600, i)) for i in xrange(1, 11)],
			[1630, 4433, 12051, 32758, 86400, 86400, 86400, 86400, 86400, 86400]
		)
		a.setBanTimeExtra('factor', '2.0 / 2.885385')
		# change max time :
		a.setBanTimeExtra('maxtime', '12h')
		self.assertEqual(
			[int(a.calcBanTime(600, i)) for i in xrange(1, 11)],
			[1200, 2400, 4800, 9600, 19200, 38400, 43200, 43200, 43200, 43200]
		)
		a.setBanTimeExtra('maxtime', '24h')
		## test randomization - not possibe all 10 times we have random = 0:
		a.setBanTimeExtra('rndtime', '5m')
		self.assertTrue(
			False in [1200 in [int(a.calcBanTime(600, 1)) for i in xrange(10)] for c in xrange(10)]
		)
		a.setBanTimeExtra('rndtime', None)
		self.assertFalse(
			False in [1200 in [int(a.calcBanTime(600, 1)) for i in xrange(10)] for c in xrange(10)]
		)
		# restore default:
		a.setBanTimeExtra('factor', None);
		a.setBanTimeExtra('multipliers', None)
		a.setBanTimeExtra('factor', None);
		a.setBanTimeExtra('maxtime', '24h')
		a.setBanTimeExtra('rndtime', None)


class BanTimeIncrDB(LogCaptureTestCase):

	def setUp(self):
		"""Call before every test case."""
		super(BanTimeIncrDB, self).setUp()
		if Fail2BanDb is None and sys.version_info >= (2,7): # pragma: no cover
			raise unittest.SkipTest(
				"Unable to import fail2ban database module as sqlite is not "
				"available.")
		elif Fail2BanDb is None:
			return
		_, self.dbFilename = tempfile.mkstemp(".db", "fail2ban_")
		self.db = Fail2BanDb(self.dbFilename)
		self.jail = None
		self.Observer = ObserverThread()

	def tearDown(self):
		"""Call after every test case."""
		super(BanTimeIncrDB, self).tearDown()
		if Fail2BanDb is None: # pragma: no cover
			return
		# Cleanup
		os.remove(self.dbFilename)

	def incrBanTime(self, ticket, banTime=None):
		jail = self.jail;
		if banTime is None:
			banTime = ticket.getBanTime(jail.actions.getBanTime())
		ticket.setBanTime(None)
		incrTime = self.Observer.incrBanTime(jail, banTime, ticket)
		#print("!!!!!!!!! banTime: %s, %s, incr: %s " % (banTime, ticket.getBanCount(), incrTime))
		return incrTime


	def testBanTimeIncr(self):
		if Fail2BanDb is None: # pragma: no cover
			return
		jail = DummyJail()
		self.jail = jail
		jail.database = self.db
		self.db.addJail(jail)
		# we tests with initial ban time = 10 seconds:
		jail.actions.setBanTime(10)
		jail.setBanTimeExtra('increment', 'true')
		jail.setBanTimeExtra('multipliers', '1 2 4 8 16 32 64 128 256 512 1024 2048')
		ip = "127.0.0.2"
		# used as start and fromtime (like now but time independence, cause test case can run slow):
		stime = int(MyTime.time())
		ticket = FailTicket(ip, stime, [])
		# test ticket not yet found
		self.assertEqual(
			[self.incrBanTime(ticket, 10) for i in xrange(3)], 
			[10, 10, 10]
		)
		# add a ticket banned
		self.db.addBan(jail, ticket)
		# get a ticket already banned in this jail:
		self.assertEqual(
			[(banCount, timeOfBan, lastBanTime) for banCount, timeOfBan, lastBanTime in self.db.getBan(ip, jail, None, False)],
			[(1, stime, 10)]
		)
		# incr time and ban a ticket again :
		ticket.setTime(stime + 15)
		self.assertEqual(self.incrBanTime(ticket, 10), 20)
		self.db.addBan(jail, ticket)
		# get a ticket already banned in this jail:
		self.assertEqual(
			[(banCount, timeOfBan, lastBanTime) for banCount, timeOfBan, lastBanTime in self.db.getBan(ip, jail, None, False)],
			[(2, stime + 15, 20)]
		)
		# get a ticket already banned in all jails:
		self.assertEqual(
			[(banCount, timeOfBan, lastBanTime) for banCount, timeOfBan, lastBanTime in self.db.getBan(ip, '', None, True)],
			[(2, stime + 15, 20)]
		)
		# search currently banned and 1 day later (nothing should be found):
		self.assertEqual(
			self.db.getCurrentBans(forbantime=-24*60*60, fromtime=stime),
			[]
		)
		# search currently banned anywhere:
		restored_tickets = self.db.getCurrentBans(fromtime=stime)
		self.assertEqual(
			str(restored_tickets),
			('[FailTicket: ip=%s time=%s bantime=20 bancount=2 #attempts=0 matches=[]]' % (ip, stime + 15))
		)
		# search currently banned:
		restored_tickets = self.db.getCurrentBans(jail=jail, fromtime=stime)
		self.assertEqual(
			str(restored_tickets), 
			('[FailTicket: ip=%s time=%s bantime=20 bancount=2 #attempts=0 matches=[]]' % (ip, stime + 15))
		)
		restored_tickets[0].setRestored(True)
		self.assertTrue(restored_tickets[0].getRestored())
		# increase ban multiple times:
		lastBanTime = 20
		for i in xrange(10):
			ticket.setTime(stime + lastBanTime + 5)
			banTime = self.incrBanTime(ticket, 10)
			self.assertEqual(banTime, lastBanTime * 2)
			self.db.addBan(jail, ticket)
			lastBanTime = banTime
		# increase again, but the last multiplier reached (time not increased):
		ticket.setTime(stime + lastBanTime + 5)
		banTime = self.incrBanTime(ticket, 10)
		self.assertNotEqual(banTime, lastBanTime * 2)
		self.assertEqual(banTime, lastBanTime)
		self.db.addBan(jail, ticket)
		lastBanTime = banTime
		# add two tickets from yesterday: one unbanned (bantime already out-dated):
		ticket2 = FailTicket(ip+'2', stime-24*60*60, [])
		ticket2.setBanTime(12*60*60)
		self.db.addBan(jail, ticket2)
		# and one from yesterday also, but still currently banned :
		ticket2 = FailTicket(ip+'1', stime-24*60*60, [])
		ticket2.setBanTime(36*60*60)
		self.db.addBan(jail, ticket2)
		# search currently banned:
		restored_tickets = self.db.getCurrentBans(fromtime=stime)
		self.assertEqual(len(restored_tickets), 2)
		self.assertEqual(
			str(restored_tickets[0]),
			'FailTicket: ip=%s time=%s bantime=%s bancount=13 #attempts=0 matches=[]' % (ip, stime + lastBanTime + 5, lastBanTime)
		)
		self.assertEqual(
			str(restored_tickets[1]),
			'FailTicket: ip=%s time=%s bantime=%s bancount=1 #attempts=0 matches=[]' % (ip+'1', stime-24*60*60, 36*60*60)
		)
		# search out-dated (give another fromtime now is -18 hours):
		restored_tickets = self.db.getCurrentBans(fromtime=stime-18*60*60)
		self.assertEqual(len(restored_tickets), 3)
		self.assertEqual(
			str(restored_tickets[2]),
			'FailTicket: ip=%s time=%s bantime=%s bancount=1 #attempts=0 matches=[]' % (ip+'2', stime-24*60*60, 12*60*60)
		)
		# should be still banned
		self.assertFalse(restored_tickets[1].isTimedOut(stime))
		self.assertFalse(restored_tickets[1].isTimedOut(stime))
		# the last should be timed out now
		self.assertTrue(restored_tickets[2].isTimedOut(stime))
		self.assertFalse(restored_tickets[2].isTimedOut(stime-18*60*60))

		# test permanent, create timed out:
		ticket=FailTicket(ip+'3', stime-36*60*60, [])
		self.assertTrue(ticket.isTimedOut(stime, 600))
		# not timed out - permanent jail:
		self.assertFalse(ticket.isTimedOut(stime, -1))
		# not timed out - permanent ticket:
		ticket.setBanTime(-1)
		self.assertFalse(ticket.isTimedOut(stime, 600))
		self.assertFalse(ticket.isTimedOut(stime, -1))
		# timed out - permanent jail but ticket time (not really used behavior)
		ticket.setBanTime(600)
		self.assertTrue(ticket.isTimedOut(stime, -1))

		# get currently banned pis with permanent one:
		ticket.setBanTime(-1)
		self.db.addBan(jail, ticket)
		restored_tickets = self.db.getCurrentBans(fromtime=stime)
		self.assertEqual(len(restored_tickets), 3)
		self.assertEqual(
			str(restored_tickets[2]),
			'FailTicket: ip=%s time=%s bantime=%s bancount=1 #attempts=0 matches=[]' % (ip+'3', stime-36*60*60, -1)
		)
		# purge (nothing should be changed):
		self.db.purge()
		restored_tickets = self.db.getCurrentBans(fromtime=stime)
		self.assertEqual(len(restored_tickets), 3)
		# set short time and purge again:
		ticket.setBanTime(600)
		self.db.addBan(jail, ticket)
		self.db.purge()
		# this old ticket should be removed now:
		restored_tickets = self.db.getCurrentBans(fromtime=stime)
		self.assertEqual(len(restored_tickets), 2)
		self.assertEqual(restored_tickets[0].getIP(), ip)

    # purge remove 1st ip
		self.db._purgeAge = -48*60*60
		self.db.purge()
		restored_tickets = self.db.getCurrentBans(fromtime=stime)
		self.assertEqual(len(restored_tickets), 1)
		self.assertEqual(restored_tickets[0].getIP(), ip+'1')

    # this should purge all bans, bips and logs - nothing should be found now
		self.db._purgeAge = -240*60*60
		self.db.purge()
		restored_tickets = self.db.getCurrentBans(fromtime=stime)
		self.assertEqual(restored_tickets, [])

    # two separate jails :
		jail1 = DummyJail()
		jail1.database = self.db
		self.db.addJail(jail1)
		jail2 = DummyJail()
		jail2.database = self.db
		self.db.addJail(jail2)
		ticket1 = FailTicket(ip, stime, [])
		ticket1.setBanTime(6000)
		self.db.addBan(jail1, ticket1)
		ticket2 = FailTicket(ip, stime-6000, [])
		ticket2.setBanTime(12000)
		ticket2.setBanCount(1)
		self.db.addBan(jail2, ticket2)
		restored_tickets = self.db.getCurrentBans(jail=jail1, fromtime=stime)
		self.assertEqual(len(restored_tickets), 1)
		self.assertEqual(
			str(restored_tickets[0]),
			'FailTicket: ip=%s time=%s bantime=%s bancount=1 #attempts=0 matches=[]' % (ip, stime, 6000)
		)
		restored_tickets = self.db.getCurrentBans(jail=jail2, fromtime=stime)
		self.assertEqual(len(restored_tickets), 1)
		self.assertEqual(
			str(restored_tickets[0]),
			'FailTicket: ip=%s time=%s bantime=%s bancount=2 #attempts=0 matches=[]' % (ip, stime-6000, 12000)
		)
    # get last ban values for this ip separately for each jail:
		for row in self.db.getBan(ip, jail1):
			self.assertEqual(row, (1, stime, 6000))
			break
		for row in self.db.getBan(ip, jail2):
			self.assertEqual(row, (2, stime-6000, 12000))
			break
    # get max values for this ip (over all jails):
		for row in self.db.getBan(ip, overalljails=True):
			self.assertEqual(row, (3, stime, 18000))
			break


class ObserverTest(unittest.TestCase):

	def setUp(self):
		"""Call before every test case."""
		#super(ObserverTest, self).setUp()
		pass

	def tearDown(self):
		#super(ObserverTest, self).tearDown()
		pass

	def testObserverBanTimeIncr(self):
		obs = ObserverThread()
		obs.start()
		# wait for idle
		obs.wait_idle(0.1)
		# observer will sleep 0.5 second (in busy state):
		o = set(['test'])
		obs.add('call', o.clear)
		obs.add('call', o.add, 'test2')
		obs.wait_empty(1)
		self.assertFalse(obs.is_full)
		self.assertEqual(o, set(['test2']))
		# observer makes pause
		obs.paused = True
		# observer will sleep 0.5 second after pause ends:
		obs.add('call', o.clear)
		obs.add('call', o.add, 'test3')
		obs.wait_empty(0.25)
		self.assertTrue(obs.is_full)
		self.assertEqual(o, set(['test2']))
		obs.paused = False
		# wait running:
		obs.wait_empty(1)
		self.assertEqual(o, set(['test3']))

		self.assertTrue(obs.is_active())
		self.assertTrue(obs.is_alive())
		obs.stop()
		obs = None