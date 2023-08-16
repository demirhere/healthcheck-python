### A Health Check API Library for Multiprocessing Python Apps

[![license](https://img.shields.io/badge/license-Apache%202-blue)](LICENSE)

This library adds a health check REST API to your multiprocessing apps. You can add health check function calls to your 
functions and library will track the function calls. This library supports ```multiprocessing``` threads. You can fetch
a single overall app status by fetching
```http://<ip>:<port>/healthcheck```, a single overall app liveness by fetching
```http://<ip>:<port>/liveness```. 

Influenced by prometheus client mp exporter. Health check functions will write healthy and liveness results `<pid>.json` 
file located in directory defined by `PY_HEALTH_MULTIPROC_DIR`. If the directory doesn't exist, health checks won't work. 

**Please clear the directory content before running your app.** REST API 

Each health check class will be run every 10 seconds by default. You can change this value by setting `PY_HEALTH_RUN_PERIOD`.

#### Usage

You can register your functions with ```add_check()``` decorator.
You can set a timeout for your functions with ```set_timeout()``` if you process needs to check in regularly.

```python
import multiprocessing as mp
import time

import healthcheck_python as hp


class P1(mp.Process):
	def __init__(self, timeout=0):
		super().__init__()
		self._stop_bit = mp.Event()
		self.timeout = timeout

	def close(self) -> None:
		self._stop_bit.set()

	def healthcheck(self):
		return True, "Healthcheck is OK"

	def do_something(self):
		time.sleep(5)

	def run(self):
		hp.add_check(self.healthcheck)
		hp.set_timeout(self.timeout)

		hp.live()
		while not self._stop_bit.is_set():
			hp.healthy()
			self.do_something()


hp.start_http_server(port=8080)

p1 = P1(timeout=10)
p1.start()

p2 = P1()
p2.start()

time.sleep(30)

p1.close()
p2.close()

p1.join()
p2.join()
```

```shell
$ curl http://localhost:8080/healthcheck
{"hostname": "my_app", "status": "success", "timestamp": 1684406235.474363, "results": [[{"checker": "healthcheck", "output": "Healthcheck is OK", "passed": true, "timestamp": 1684406230.9507005, "response_time": 5e-06}, {"checker": "P1", "output": "", "passed": true, "timestamp": 1684406230.9507082, "response_time": 0}]]}
$ curl http://localhost:8080/liveness
{"hostname": "my_app", "liveness": true, "timestamp": 1684406208.784097}
```