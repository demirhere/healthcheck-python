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

import json
import logging
import os
import socket
import sys
import threading
import time
import urllib
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Tuple, Dict, Any
from wsgiref.handlers import SimpleHandler

from healthcheck_python.release import __version__

__all__ = ['WSGIServer', 'WSGIRequestHandler', 'make_server', 'start_http_server']

SERVER_VERSION = "WSGIServer/" + __version__


def json_output_handler(results, passed: bool):
	"""
	Creates a JSON output for the healthcheck
	:param results: health check results
	:param passed: overall health check status
	:return: JSON output
	"""
	data = {
		'hostname': socket.gethostname(),
		'status': 'success' if passed else 'failure',
		'timestamp': time.time(),
		'results': results,
	}
	return data


def json_liveness_handler(liveness: bool):
	"""
	Creates a JSON output for the liveness check
	:param liveness: Overall liveness status
	:return: JSON output
	"""
	data = {
		'hostname': socket.gethostname(),
		'liveness': liveness,
		'timestamp': time.time(),
	}
	return data


class HealthCollector:
	"""
	Collects the results of the health checks
	"""

	def __init__(self):
		self._dump_dir = os.environ.get('PY_HEALTH_MULTIPROC_DIR', None)
		if self._dump_dir:
			if not os.path.exists(self._dump_dir):
				logging.warning("PY_HEALTH_MULTIPROC_DIR not set, healthcheck will not work")
				self._dump_dir = None
				return

			if not os.path.isdir(self._dump_dir):
				logging.warning("PY_HEALTH_MULTIPROC_DIR is not a directory, healthcheck will not work")
				self._dump_dir = None

	def health(self) -> Tuple[bool, Dict[str, Any]]:
		"""
		Collects the results of the health checks
		:return: health check results
		"""
		if not self._dump_dir:
			return False, {'status': 'failure', 'message': 'PY_HEALTH_MULTIPROC_DIR not set'}

		results = []
		statuses = []
		for file in os.listdir(self._dump_dir):
			with open(os.path.join(self._dump_dir, file), 'r') as json_file:
				try:
					data = json.load(json_file)
				except json.JSONDecodeError:
					continue

			if data['timeout'] == 0:
				status = data['status']
			else:
				status = (time.time() - data['timestamp'] < data['timeout']) and data['status']
				data['status'] = status

			statuses.append(status)
			results.append(data)

		overall_status = all(statuses)
		return overall_status, json_output_handler(results, overall_status)

	def liveness(self) -> Tuple[bool, Dict[str, Any]]:
		"""
		Collects the results of the liveness checks
		:return: liveness check results
		"""

		if not self._dump_dir:
			return False, {'liveness': 'failure', 'message': 'PY_HEALTH_MULTIPROC_DIR not set'}

		liveness = []
		for file in os.listdir(self._dump_dir):
			with open(os.path.join(self._dump_dir, file), 'r') as json_file:
				try:
					data = json.load(json_file)
				except json.JSONDecodeError:
					continue

			liveness.append(data['liveness'])

		overall_liveness = all(liveness)
		return overall_liveness, json_liveness_handler(overall_liveness)


class WSGIServer(HTTPServer):
	"""BaseHTTPServer that implements the Python WSGI protocol"""

	applications = {}

	def server_bind(self):
		"""
		Override server_bind to store the server name.
		"""
		HTTPServer.server_bind(self)
		self.setup_environ()

	def setup_environ(self):
		"""
		Override setup_environ to add the server name.
		:return:
		"""
		env = self.base_environ = {}
		env['SERVER_NAME'] = self.server_name
		env['GATEWAY_INTERFACE'] = 'CGI/1.1'
		env['SERVER_PORT'] = str(self.server_port)
		env['REMOTE_HOST'] = ''
		env['CONTENT_LENGTH'] = ''
		env['SCRIPT_NAME'] = ''

	def get_app(self, path: str) -> Callable:
		"""
		Get the application for the given path.
		:param path: URI path
		:return: application
		"""
		return self.applications.get(path)

	def set_app(self, path: str, application: Callable) -> None:
		"""
		Set the application for the given path.
		:param path: URI path
		:param application: application
		"""
		self.applications[path] = application


class WSGIRequestHandler(BaseHTTPRequestHandler):
	"""
	A request handler that implements WSGI dispatching.
	"""
	SERVER_VERSION = "WSGIServer/" + __version__

	def get_environ(self):
		"""
		Create a WSGI environment.
		"""
		env = self.server.base_environ.copy()
		env['SERVER_PROTOCOL'] = self.request_version
		env['SERVER_SOFTWARE'] = self.server_version
		env['REQUEST_METHOD'] = self.command
		if '?' in self.path:
			path, query = self.path.split('?', 1)
		else:
			path, query = self.path, ''

		env['PATH_INFO'] = urllib.parse.unquote(path, 'iso-8859-1')
		env['QUERY_STRING'] = query

		host = self.address_string()
		if host != self.client_address[0]:
			env['REMOTE_HOST'] = host
		env['REMOTE_ADDR'] = self.client_address[0]

		if self.headers.get('content-type') is None:
			env['CONTENT_TYPE'] = self.headers.get_content_type()
		else:
			env['CONTENT_TYPE'] = self.headers['content-type']

		length = self.headers.get('content-length')
		if length:
			env['CONTENT_LENGTH'] = length

		for key, value in self.headers.items():
			key = key.replace('-', '_').upper()
			value = value.strip()
			if key in env:
				continue  # skip content length, type,etc.
			if 'HTTP_' + key in env:
				env['HTTP_' + key] += ',' + value  # comma-separate multiple headers
			else:
				env['HTTP_' + key] = value
		return env

	def get_stderr(self):
		"""
		Return sys.stderr
		"""
		return sys.stderr

	def handle(self):
		"""
		Handle a single HTTP request.
		"""
		self.raw_requestline = self.rfile.readline(65537)
		if len(self.raw_requestline) > 65536:
			self.requestline = ''
			self.request_version = ''
			self.command = ''
			self.send_error(414)
			return

		if not self.parse_request():  # An error code has been sent, just exit
			return

		path = self.path
		output = self.server.get_app(path)

		if output is not None:
			handler = SimpleHandler(
				self.rfile, self.wfile, self.get_stderr(), self.get_environ(),
				multithread=False,
			)
			handler.request_handler = self  # backpointer for logging
			handler.run(output)


def make_wsgi_app(app: Callable) -> Callable:
	"""
	Converts a health check function into a WSGI application.
	:param app: health check function
	:return: WSGI application
	"""

	def health_app(_, start_response):
		status, output = app()
		status_str = "200 OK" if status else "500 Internal Server Error"
		start_response(status_str, [('Content-Type', 'application/json')])
		return [json.dumps(output).encode("utf-8")]

	return health_app


def make_server(host, port, app):
	"""
	Create a WSGI server.
	:param host: Listen address
	:param port: Listen port
	:param app: HealthCollector application
	:return: WSIG server
	"""
	server = WSGIServer((host, port), WSGIRequestHandler)

	app_health = make_wsgi_app(app.health)
	server.set_app("/healthcheck", app_health)

	app_liveness = make_wsgi_app(app.liveness)
	server.set_app("/liveness", app_liveness)
	return server


def start_http_server(addr: str = "0.0.0.0", port: int = 0):
	"""
	Starts an HTTP server for health checks.
	:param addr: Listen address
	:param port: Listen port
	"""
	server = make_server(addr, port, HealthCollector())

	thread = threading.Thread(target=server.serve_forever)
	thread.daemon = True
	thread.start()
