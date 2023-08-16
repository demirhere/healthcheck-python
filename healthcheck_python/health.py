#  Copyright (c) 2021.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import inspect
import json
import logging
import os
import threading
import time
from functools import reduce
from typing import Dict, List, Callable

logger = logging.getLogger(__name__)


def add_check(function: Callable) -> None:
	"""
	Add a health check function to the list of health check functions
	:param function: a function that returns a dictionary with the health check results
	"""
	CHECKS.append(function)


def set_timeout(timeout: int, caller: str = None) -> None:
	"""
	Set the timeout for the periodic call to the healthcheck function
	:param timeout: timeout in seconds
	:param caller: Optional name of the caller. If not provided, the name of the class is used
	"""
	if not THREAD.is_alive():
		stack = inspect.stack()
		if caller is None:
			caller = stack[1][0].f_locals["self"].__class__.__name__
		THREAD.prefix = caller
		THREAD.timeout = timeout
		THREAD.start()


def healthy():
	"""
	Mark the service as healthy
	This function has to be called periodically to mark the service as healthy
	"""
	THREAD.check_in()


def live():
	"""
	Mark the service as live
	"""
	THREAD.live()


def json_output_handler(results: List, passed: bool, liveness: bool) -> Dict:
	"""
	Create a json output for individual health check process
	:param results: The output of the health check function
	:param passed: Overall health check result
	:param liveness: Liveness check result
	:return: json output
	"""
	data = {
		'name': THREAD.prefix,
		'status': passed,
		'liveness': liveness,
		'timestamp': time.time(),
		'timeout': THREAD.timeout,
		'results': results,
	}
	return data


def check_reduce(passed, result):
	"""
	Reduce function to check if all the health check functions passed
	"""
	return passed and result.get('passed')


class HealthCheck(threading.Timer):
	"""
	Health check timer function. Runs every interval seconds and calls the health check functions
	"""

	def __init__(self, interval: int, prefix="", args=None, kwargs=None):
		super().__init__(interval, self.run, args, kwargs)
		self._stop_event = threading.Event()
		self.prefix: str = prefix
		self.daemon = True
		self.timeout: int = 0
		self._latest_checkin = 0
		self._liveness: bool = False

		self._dump_dir = os.environ.get('PY_HEALTH_MULTIPROC_DIR', None)
		if self._dump_dir:
			if not os.path.exists(self._dump_dir):
				self._dump_dir = None
				return

			if not os.path.isdir(self._dump_dir):
				self._dump_dir = None

	def stop(self):
		"""
		Stop the timer
		"""
		self._stop_event.set()

	def check_in(self):
		"""
		Check in
		"""
		self._latest_checkin = time.time()

	def run(self):
		"""
		Start the timer
		"""
		while not self._stop_event.is_set():
			if self._dump_dir:
				self._check_health()
			self._stop_event.wait(self.interval)

	def _check_health(self) -> None:
		"""
		Check health
		"""
		results = []
		# check registered health check functions
		for check in CHECKS:
			results.append(self.run_check(check))

		# periodic checkin is only checked if timeout is set
		if self.timeout > 0:
			periodic_checkin = self.check_periodic_checkin()
			results.append(periodic_checkin)

		passed = reduce(check_reduce, results, True)
		message = json_output_handler(results, passed, self._liveness)

		# dump to file for collection
		with open(os.path.join(self._dump_dir, f"{os.getpid()}.json"), "w") as json_file:
			json.dump(message, json_file)

	def run_check(self, check: Callable) -> Dict:
		"""
		Run the health check function
		:param check: a registered health check function
		:return:
		"""
		start_time = time.time()

		try:
			passed, output = check()
		except Exception as exc:
			logger.exception(exc)
			passed, output = False, str(exc)

		end_time = time.time()
		elapsed_time = end_time - start_time
		# Reduce to 6 decimal points to have consistency with timestamp
		elapsed_time = float(f"{elapsed_time:.6f}")

		if passed:
			logger.debug("Health check %s.%s passed", self.prefix, check.__name__)
		else:
			logger.error("Health check %s.%s failed with output %s", self.prefix, check.__name__, output)

		timestamp = time.time()

		result = {
			'checker': check.__name__,
			'output': output,
			'passed': passed,
			'timestamp': timestamp,
			'response_time': elapsed_time
		}
		return result

	def check_periodic_checkin(self) -> Dict:
		"""
		Check if the periodic checkin is within the timeout
		"""
		periodic_check = {
			'checker': self.prefix,
			'output': '',
			'passed': False,
			'timestamp': time.time(),
			'response_time': 0,
		}

		time_diff = time.time() - self._latest_checkin
		if time_diff > self.timeout:
			periodic_check['passed'] = False
		else:
			periodic_check['passed'] = True
		return periodic_check

	def live(self) -> None:
		"""
		Mark the service as live
		"""
		self._liveness = True


CHECKS = []

RUN_PERIOD = os.environ.get('PY_HEALTH_RUN_PERIOD', 5)
THREAD = HealthCheck(RUN_PERIOD)
