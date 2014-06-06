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
# This module was written as part of ban time increment feature.

__author__ = "Serg G. Brester (sebres)"
__copyright__ = "Copyright (c) 2014 Serg G. Brester"
__license__ = "GPL"

import time, logging
import threading
import os, datetime, math, json, random
import sys
if sys.version_info >= (3, 3):
	import importlib.machinery
else:
	import imp
from .jailthread import JailThread
from .mytime import MyTime

# Gets the instance of the logger.
logSys = logging.getLogger(__name__)

class ObserverThread(threading.Thread):
	"""Handles observing a database, managing bad ips and ban increment.

	Parameters
	----------

	Attributes
	----------
	daemon
	ident
	name
	status
	active : bool
		Control the state of the thread.
	idle : bool
		Control the idle state of the thread.
	sleeptime : int
		The time the thread sleeps for in the loop.
	"""

	def __init__(self):
		self.active = False
		self.idle = False
		## Event queue
		self._queue_lock = threading.RLock()
		self._queue = []
		## Event, be notified if anything added to event queue
		self._notify = threading.Event()
		## Sleep for max 60 seconds, it possible to specify infinite to always sleep up to notifying via event, 
		## but so we can later do some service "events" occurred infrequently directly in main loop of observer (not using queue)
		self.sleeptime = 60
		#
		self._started = False
		self._timers = {}
		self._paused = False
		self.__db = None
		self.__db_purge_interval = 60*60
    # start thread
		super(ObserverThread, self).__init__(name='Observer')
		# observer is a not main thread:
		self.daemon = True

	def __getitem__(self, i):
		try:
			return self._queue[i]
		except KeyError:
			raise KeyError("Invalid event index : %s" % i)

	def __delitem__(self, name):
		try:
			del self._queue[i]
		except KeyError:
			raise KeyError("Invalid event index: %s" % i)

	def __iter__(self):
		return iter(self._queue)

	def __len__(self):
		return len(self._queue)

	def __eq__(self, other): # Required for Threading
		return False

	def __hash__(self): # Required for Threading
		return id(self)

	def add_named_timer(self, name, starttime, *event):
		"""Add a named timer event to queue will start (and wake) in 'starttime' seconds
		
		Previous timer event with same name will be canceled and trigger self into 
		queue after new 'starttime' value
		"""
		t = self._timers.get(name, None)
		if t is not None:
			t.cancel()
		t = threading.Timer(starttime, self.add, event)
		self._timers[name] = t
		t.start()

	def add_timer(self, starttime, *event):
		"""Add a timer event to queue will start (and wake) in 'starttime' seconds
		"""
		t = threading.Timer(starttime, self.add, event)
		t.start()

	def pulse_notify(self):
		"""Notify wakeup (sets and resets notify event)
		"""
		if not self._paused and self._notify:
			self._notify.set()
			self._notify.clear()

	def add(self, *event):
		"""Add a event to queue and notify thread to wake up.
		"""
		## lock and add new event to queue:
		with self._queue_lock:
			self._queue.append(event)
		self.pulse_notify()

	def call_lambda(self, l, *args):
		l(*args)

	def run(self):
		"""Main loop for Threading.

		This function is the main loop of the thread.

		Returns
		-------
		bool
			True when the thread exits nicely.
		"""
		logSys.info("Observer start...")
		## first time create named timer to purge database each hour (clean old entries) ...
		self.add_named_timer('DB_PURGE', self.__db_purge_interval, 'db_purge')
		## Mapping of all possible event types of observer:
		__meth = {
			'failureFound': self.failureFound,
			'banFound': self.banFound,
			# universal lambda:
			'call': self.call_lambda,
			# system and service events:
			'db_set': self.db_set,
			'db_purge': self.db_purge,
			# service events of observer self:
			'is_alive' : self.is_alive,
			'is_active': self.is_active,
			'start': self.start,
			'stop': self.stop,
			'shutdown': lambda:()
		}
		try:
			## check it self with sending is_alive event
			self.add('is_alive')
			## if we should stop - break a main loop
			while self.active:
				## going sleep, wait for events (in queue)
				self.idle = True
				self._notify.wait(self.sleeptime)
				# does not clear notify event here - we use pulse (and clear it inside) ...
				# ## wake up - reset signal now (we don't need it so long as we reed from queue)
				# if self._notify:
				#  	self._notify.clear()
				if self._paused:
					continue
				self.idle = False
				## check events available and execute all events from queue
				while not self._paused:
					## lock, check and pop one from begin of queue:
					try:
						ev = None
						with self._queue_lock:
							if len(self._queue):
								ev = self._queue.pop(0)
						if ev is None:
							break
						## retrieve method by name
						meth = __meth[ev[0]]
						## execute it with rest of event as variable arguments
						meth(*ev[1:])
					except Exception as e:
						#logSys.error('%s', e, exc_info=logSys.getEffectiveLevel()<=logging.DEBUG)
						logSys.error('%s', e, exc_info=True)
				## end of main loop - exit
		except Exception as e:
			logSys.error('Observer stopped after error: %s', e, exc_info=True)
			#print("Observer stopped with error: %s" % str(e))
			self.idle = True
			return True
		logSys.info("Observer stopped, %s events remaining.", len(self._queue))
		#print("Observer stopped, %s events remaining." % len(self._queue))
		self.idle = True
		return True

	def is_alive(self):
		#logSys.debug("Observer alive...")
		return True

	def is_active(self, fromStr=None):
		# logSys.info("Observer alive, %s%s", 
		# 	'active' if self.active else 'inactive', 
		# 	'' if fromStr is None else (", called from '%s'" % fromStr))
		return self.active

	def start(self):
		with self._queue_lock:
			if not self.active:
				self.active = True
				super(ObserverThread, self).start()

	def stop(self):
		logSys.info("Observer stop ...")
		#print("Observer stop ....")
		self.active = False
		if self._notify:
			# just add shutdown job to make possible wait later until full (events remaining)
			self.add('shutdown')
			self.pulse_notify()
			self._notify = None
			# wait max 5 seconds until full (events remaining)
			self.wait_empty(5)

	@property
	def is_full(self):
		with self._queue_lock:
			return True if len(self._queue) else False

	def wait_empty(self, sleeptime=None):
		"""Wait observer is running and returns if observer has no more events (queue is empty)
		"""
		if not self.is_full:
			return True
		if sleeptime is not None:
			e = MyTime.time() + sleeptime
		while self.is_full:
			if sleeptime is not None and MyTime.time() > e:
				break
			time.sleep(0.1)
		return not self.is_full


	def wait_idle(self, sleeptime=None):
		"""Wait observer is running and returns if observer idle (observer sleeps)
		"""
		time.sleep(0.001)
		if self.idle:
			return True
		if sleeptime is not None:
			e = MyTime.time() + sleeptime
		while not self.idle:
			if sleeptime is not None and MyTime.time() > e:
				break
			time.sleep(0.1)
		return self.idle

	@property
	def paused(self):
		return self._paused;

	@paused.setter
	def paused(self, pause):
		if self._paused == pause:
			return
		self._paused = pause
		# wake after pause ended
		self.pulse_notify()


	@property
	def status(self):
		"""Status of observer to be implemented. [TODO]
		"""
		return ('', '')

	## -----------------------------------------
	## [Async] database service functionality ...
	## -----------------------------------------

	def db_set(self, db):
		self.__db = db

	def db_purge(self):
		logSys.info("Purge database event occurred")
		if self.__db is not None:
			self.__db.purge()
		# trigger timer again ...
		self.add_named_timer('DB_PURGE', self.__db_purge_interval, 'db_purge')

	## -----------------------------------------
	## [Async] ban time increment functionality ...
	## -----------------------------------------

	def failureFound(self, failManager, jail, ticket):
		""" Notify observer a failure for ip was found

		Observer will check ip was known (bad) and possibly increase an retry count
		"""
		# check jail active :
		if not jail.is_alive():
			return
		ip = ticket.getIP()
		unixTime = ticket.getTime()
		logSys.info("[%s] Observer: failure found %s", jail.name, ip)
		# increase retry count for known (bad) ip, corresponding banCount of it (one try will count than 2, 3, 5, 9 ...)  :
		banCount = 0
		retryCount = 1
		timeOfBan = None
		try:
			db = jail.database
			if db is not None:
				for banCount, timeOfBan, lastBanTime in db.getBan(ip, jail):
					retryCount = ((1 << (banCount if banCount < 20 else 20))/2 + 1)
					# if lastBanTime == -1 or timeOfBan + lastBanTime * 2 > MyTime.time():
					# 	retryCount = failManager.getMaxRetry()
					break
				retryCount = min(retryCount, failManager.getMaxRetry())
				# check this ticket already known (line was already processed and in the database and will be restored from there):
				if timeOfBan is not None and unixTime <= timeOfBan:
					logSys.info("[%s] Ignore failure %s before last ban %s < %s, restored"
								 % (jail.name, ip, unixTime, timeOfBan))
					return
			# for not increased failures observer should not add it to fail manager, because was already added by filter self
			if retryCount <= 1:
				return
			# retry counter was increased - add it again:
			logSys.info("[%s] Found %s, bad - %s, %s # -> %s, ban", jail.name, ip, 
				datetime.datetime.fromtimestamp(unixTime).strftime("%Y-%m-%d %H:%M:%S"), banCount, retryCount)
			# remove matches from this ticket, because a ticket was already added by filter self
			ticket.setMatches(None)
			# retryCount-1, because a ticket was already once incremented by filter self
			failManager.addFailure(ticket, retryCount - 1, True)

			# after observe we have increased count >= maxretry ...
			if retryCount >= failManager.getMaxRetry():
				# perform the banning of the IP now (again)
				# [todo]: this code part will be used multiple times - optimize it later.
				try: # pragma: no branch - exception is the only way out
					while True:
						ticket = failManager.toBan(ip)
						jail.putFailTicket(ticket)
				except Exception:
					failManager.cleanup(MyTime.time())

		except Exception as e:
			logSys.error('%s', e, exc_info=logSys.getEffectiveLevel()<=logging.DEBUG)
			#logSys.error('%s', e, exc_info=True)


	class BanTimeIncr:
		def __init__(self, banTime, banCount):
			self.Time = banTime
			self.Count = banCount

	def calcBanTime(self, jail, banTime, banCount):
		be = jail.getBanTimeExtra()
		return be['evformula'](self.BanTimeIncr(banTime, banCount))

	def incrBanTime(self, jail, banTime, ticket):
		"""Check for IP address to increment ban time (if was already banned).

		Returns
		-------
		float
			new ban time.
		"""
		# check jail active :
		if not jail.is_alive():
			return
		be = jail.getBanTimeExtra()
		ip = ticket.getIP()
		orgBanTime = banTime
		# check ip was already banned (increment time of ban):
		try:
			if banTime > 0 and be.get('increment', False):
				# search IP in database and increase time if found:
				for banCount, timeOfBan, lastBanTime in \
					jail.database.getBan(ip, jail, overalljails=be.get('overalljails', False)) \
				:
					logSys.debug('IP %s was already banned: %s #, %s' % (ip, banCount, timeOfBan));
					ticket.setBanCount(banCount);
					# calculate new ban time
					if banCount > 0:
						banTime = be['evformula'](self.BanTimeIncr(banTime, banCount))
					ticket.setBanTime(banTime);
					# check current ticket time to prevent increasing for twice read tickets (restored from log file besides database after restart)
					if ticket.getTime() > timeOfBan:
						logSys.info('[%s] IP %s is bad: %s # last %s - incr %s to %s' % (jail.name, ip, banCount, 
							datetime.datetime.fromtimestamp(timeOfBan).strftime("%Y-%m-%d %H:%M:%S"), 
							datetime.timedelta(seconds=int(orgBanTime)), datetime.timedelta(seconds=int(banTime))));
					else:
						ticket.setRestored(True)
					break
		except Exception as e:
			logSys.error('%s', e, exc_info=logSys.getEffectiveLevel()<=logging.DEBUG)
			#logSys.error('%s', e, exc_info=True)
		return banTime

	def banFound(self, ticket, jail, btime):
		""" Notify observer a ban occured for ip

		Observer will check ip was known (bad) and possibly increase/prolong a ban time
		Secondary we will actualize the bans and bips (bad ip) in database
		"""
		oldbtime = btime
		ip = ticket.getIP()
		logSys.info("[%s] Observer: ban found %s, %s", jail.name, ip, btime)
		try:
			# if not permanent, not restored and ban time was not set - check time should be increased:
			if btime != -1 and not ticket.getRestored() and ticket.getBanTime() is None:
				btime = self.incrBanTime(jail, btime, ticket)
				# if we should prolong ban time:
				if btime == -1 or btime > oldbtime:
					ticket.setBanTime(btime)
			# if not permanent
			if btime != -1:
				bendtime = ticket.getTime() + btime
				logtime = (datetime.timedelta(seconds=int(btime)),
					datetime.datetime.fromtimestamp(bendtime).strftime("%Y-%m-%d %H:%M:%S"))
				# check ban is not too old :
				if bendtime < MyTime.time():
					logSys.info('Ignore old bantime %s', logtime[1])
					return False
			else:
				logtime = ('permanent', 'infinite')
			# if ban time was prolonged - log again with new ban time:
			if btime != oldbtime:
				logSys.notice("[%s] Increase Ban %s (%d # %s -> %s)", jail.name, 
					ip, ticket.getBanCount()+1, *logtime)
			# add ticket to database, but only if was not restored (not already read from database):
			if jail.database is not None and not ticket.getRestored():
				# add to database always only after ban time was calculated an not yet already banned:
				jail.database.addBan(jail, ticket)
		except Exception as e:
			logSys.error('%s', e, exc_info=logSys.getEffectiveLevel()<=logging.DEBUG)
			#logSys.error('%s', e, exc_info=True)

# Global observer initial created in server (could be later rewriten via singleton)
class _Observers:
	def __init__(self):
		self.Main = None

Observers = _Observers()