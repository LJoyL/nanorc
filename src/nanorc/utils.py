import threading
import queue
import time
from typing import NoReturn
from multiprocessing import Process
from flask import request
import logging


class FlaskManager(threading.Thread):
    def __init__(self, name, app, port):
        threading.Thread.__init__(self)
        self.log = logging.getLogger(f"{name}-flaskmanager")
        self.name = name
        self.app = app
        self.flask = None
        self.port = port

        self.ready = False
        self.ready_lock = threading.Lock()

    def _create_flask(self) -> Process:
        need_ready = True
        need_shutdown = True

        for rule in self.app.url_map.iter_rules():
            if rule.endpoint == "readystatus":
                need_ready = False
            if rule.endpoint == "shutdown":
                need_shutdown = False


        def get_ready_status():
            return "ready"

        # no clue how to do that, so multiprocessing.Process.terminate it will be.
        # def shutdown():
        #     func = request.environ.get('werkzeug.server.shutdown')
        #     if func is None:
        #         raise RuntimeError('Not running with the Werkzeug Server')
        #     func()

        if need_ready:
            self.app.add_url_rule("/readystatus", "get_ready_status", get_ready_status, methods=["GET"])
        if need_shutdown:
            pass
            # self.app.add_url_rule("/shutdown", "get", shutdown, methods=["GET"])

        thread_name = f'{self.name}_thread'
        flask_srv = Process(target=self.app.run, kwargs={"host": "0.0.0.0", "port": self.port}, name=thread_name)
        flask_srv.daemon = False
        flask_srv.start()
        self.log.info(f'{self.name} Flask lives on PID: {flask_srv.pid}')
        ## app.is_ready() would be good here, rather than horrible polling inside a try
        tries=0

        from requests import get

        while True:
            if tries>20:
                self.log.error(f'Cannot ping the {self.name}!')
                self.log.error('This can happen if the web proxy is on at NP04.'+
                               '\nExit NanoRC and try again after executing:'+
                               '\nsource ~np04daq/bin/web_proxy.sh -u')
                raise RuntimeError(f"Cannot create a {self.name}")
            tries += 1
            try:
                resp = get(f"http://0.0.0.0:{self.port}/readystatus")
                if resp.text == "ready":
                    break
            except Exception as e:
                pass
            time.sleep(0.5)

        # We don't release that lock before we have received a "ready" from the listener
        with self.ready_lock:
            self.ready = True

        return flask_srv

    def stop(self) -> NoReturn:
        self.flask.terminate()
        self.flask.join()
        self.join()

    def is_ready(self):
        with self.ready_lock:
            return self.ready

    def _create_and_join_flask(self):
        with self.ready_lock:
            self.ready = False

        self.flask = self._create_flask()
        self.flask.join()
        with self.ready_lock:
            self.ready = False

        self.log.info(f'{self.name}-flaskmanager terminated')

    def run(self) -> NoReturn:
        self._create_and_join_flask()







def strip_env_for_rte(env):
    import copy as cp
    import re
    env_stripped = cp.deepcopy(env)
    for key in env.keys():
        if key in ["PATH","CET_PLUGIN_PATH","DUNEDAQ_SHARE_PATH","LD_LIBRARY_PATH","LIBRARY_PATH","PYTHONPATH"]:
            del env_stripped[key]
        if re.search(".*_SHARE", key) and key in env_stripped:
            del env_stripped[key]
    return env_stripped

def get_version():
    from os import getenv
    version = getenv("DUNE_DAQ_BASE_RELEASE")
    if not version:
        raise RuntimeError('Utils: dunedaq version not in the variable env DUNE_DAQ_BASE_RELEASE! Exit nanorc and\nexport DUNE_DAQ_BASE_RELEASE=dunedaq-vX.XX.XX\n')
    return version

def get_releases_dir():
    from os import getenv
    releases_dir = getenv("SPACK_RELEASES_DIR")
    if not releases_dir:
        raise RuntimeError('Utils: cannot get env SPACK_RELEASES_DIR! Exit nanorc and\nrun dbt-workarea-env or dbt-setup-release.')
    return releases_dir

def release_or_dev():
    from os import getenv
    is_release = getenv("DBT_SETUP_RELEASE_SCRIPT_SOURCED")
    if is_release:
        return 'rel'
    is_devenv = getenv("DBT_WORKAREA_ENV_SCRIPT_SOURCED")
    if is_devenv:
        return 'dev'
    return 'rel'

def get_rte_script():
    from os import path,getenv
    script = ''
    if release_or_dev() == 'rel':
        ver = get_version()
        releases_dir = get_releases_dir()
        script = path.join(releases_dir, ver, 'daq_app_rte.sh')

    else:
        dbt_install_dir = getenv('DBT_INSTALL_DIR')
        script = path.join(dbt_install_dir, 'daq_app_rte.sh')

    if not path.exists(script):
        raise RuntimeError(f'Couldn\'t understand where to find the rte script tentative: {script}')
    return script




class Task:
    def __init__(self, function, *args, **kwargs):
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs

class TaskEnqueuerThread(threading.Thread):
    def __init__(self, obj):
        super().__init__()
        self.obj = obj
        self.running = True
        self.queue = queue.Queue()

    def enqueue_asynchronous(self, task):
        if not self.running:
            raise Exception('Thread is stopping, cannot enqueue more tasks')
        self.queue.put(task)

    def enqueue_synchronous(self, task):
        if not self.running:
            raise Exception('Thread is not stopping, cannot enqueue more tasks')
        try:
            self.queue.join()
        except queue.Empty:
            pass
        self.queue.put(task)
        self.queue.join()

    def stop(self):
        self.running = False

    def abort(self):
        self.running = False
        self.queue.queue.clear()

    def run(self):
        while self.running or self.queue.qsize()>0:
            try:
                task = self.queue.get(block=False, timeout=0.1)
                getattr(self.obj, task.function)(*task.args, **task.kwargs)
                self.queue.task_done()
            except queue.Empty:
                #print('Queue empty, waiting for new tasks...')
                pass
            except Exception as e:
                print(f'Couldn\'t execute the function {task.function} on the object, reason: {str(e)}')
                raise e

            time.sleep(0.1)
def get_random_string(length):
    import random
    import string
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

def get_json_recursive(path):
    from pathlib import Path

    if not path is Path:
        path = Path(path)

    import json, os

    data = {}
    boot = path/"boot.json"
    if os.path.isfile(boot):
        with open(boot,'r') as f:
            data['boot'] = json.load(f)

    for filename in os.listdir(path):
        if os.path.isfile(path/filename):
            file_base, _ = os.path.splitext(filename)
            with open(path/filename,'r') as f:
                try:
                    data[file_base] = json.load(f)
                except:
                    print(f'WARNING: ignoring non-json file: {path/filename}')
        elif os.path.isdir(path/filename):
            if filename == 'data':continue # this one is special and handled below
            data[filename] = get_json_recursive(path/filename)

    if not os.path.isdir(path/'data'):
        return data

    for filename in os.listdir(path/"data"):
        with open(path/'data'/filename,'r') as f:
            app_cmd = filename.replace('.json', '').split('_')
            app = app_cmd[0]
            cmd = "_".join(app_cmd[1:])

            if not app in data:
                data[app] = {
                    cmd: json.load(f)
                }
            else:
                data[app][cmd]=json.load(f)

    return data


def parse_string(string_to_format:str, dico:dict={}) -> str:
    from string import Formatter
    fieldnames = [fname for _, fname, _, _ in Formatter().parse(string_to_format) if fname]

    if len(fieldnames)>1:
        raise RuntimeError(f"Too many fields in string {string_to_format}")
    elif len(fieldnames)==0:
        return string_to_format

    fieldname = fieldnames[0]
    try:
        string_to_format = string_to_format.format(**dico)
    except Exception as e:
        raise RuntimeError(f"Couldn't substitute {fieldname}. Aborting") from e

    return string_to_format



def main():
    class some_object():
        def __init__(self, name):
            self.name = name
            print(f'Created object {name}')

        def do_work_1(self, argument):
            print(f'[obj] Doing work 1, {argument}')
            time.sleep(1)
            print(f'[obj] Done work 1, {argument}')

        def do_work_2(self):
            print('[obj] Doing work 2')
            time.sleep(1)
            print('[obj] Done work 2')

    obj = some_object('test')
    tet = TaskEnqueuerThread(obj)
    tet.start()

    print('[main] starting an async task')
    tet.enqueue_asynchronous(Task('do_work_1', 'async test'))
    print('[main] returning directly')
    time.sleep(1.5) # wait for the async task to finish
    print('[main] starting a sync task')
    tet.enqueue_synchronous (Task('do_work_1', 'sync test'))
    print('[main] returning after work 1')
    print('[main] starting an async task')
    tet.enqueue_asynchronous(Task('do_work_2'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async1'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async2'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async3'))
    print('[main] returning directly, now adding a synchronous task, will wait before being executed')
    tet.enqueue_synchronous (Task('do_work_1', 'sync'))
    print('[main] returning after everything is done')

    tet.enqueue_asynchronous(Task('do_work_2'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async1'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async2'))
    tet.enqueue_asynchronous(Task('do_work_1', 'async3'))
    print('[main] sending stopping')
    tet.stop()
    print('[main] stopped')
    try:
        tet.enqueue_asynchronous(Task('do_work_1', 'async3'))
    except Exception as e:
        print(f'Exception: {str(e)}')

    tet.join()
    print('[main] returning after everything is done')

if __name__ == '__main__':
    print('main')
    main()