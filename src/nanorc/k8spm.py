#!/usr/bin/env python

import logging
import rich
import socket
import time
import json
import copy as cp
import os
from urllib.parse import urlparse
from kubernetes import client, config
from rich.console import Console
from rich.progress import *

class AppProcessDescriptor(object):
    """docstring for AppProcessDescriptor"""

    def __init__(self, name):
        super(AppProcessDescriptor, self).__init__()
        self.name = name
        self.host = None
        self.conf = None
        self.port = None
        self.proc = None


    def __str__(self):
        return str(vars(self))

class K8sProcess(object):

    def __init__(self, pm, name, namespace):
        self.pm = pm
        self.name = name
        self.namespace = namespace

    def is_alive(self):
        s = self.pm._core_v1_api.read_namespaced_pod_status(self.name, self.namespace)
        for cond in s.status.conditions:
            if cond.type == "Ready" and cond.status == "True":
                return True
        return False

    def status(self):
        s = self.pm._core_v1_api.read_namespaced_pod_status(self.name, self.namespace)
        container_status = s.status.container_statuses[0].state
        if   container_status.running:
            return "Running"
        elif container_status.terminated:
            return f"Terminated {container_status.terminated.exit_code} {container_status.terminated.reason}"
        elif container_status.waiting:
            return f"Waiting {container_status.waiting.reason}"
        else:
            return 'Unknown'



class K8SProcessManager(object):
    def __init__(self, console: Console, cluster_config, connections, mount_dirs):
        """A Kubernetes Process Manager

        Args:
            console (Console): Description
        """
        super(K8SProcessManager, self).__init__()
        self.log = logging.getLogger(__name__)
        self.connections = connections
        self.mount_dirs = mount_dirs
        self.mount_cvmfs = True
        self.console = console
        self.apps = {}
        self.partition = None
        self.cluster_config = cluster_config

        config.load_kube_config()

        self._core_v1_api = client.CoreV1Api()
        self._apps_v1_api = client.AppsV1Api()



    def list_pods(self):
        self.log.info("Listing pods with their IPs:")
        ret = self._core_v1_api.list_pod_for_all_namespaces(watch=False)
        for i in ret.items:
            self.log.info("%s\t%s\t%s" % (i.status.pod_ip, i.metadata.namespace, i.metadata.name))

    def list_endpoints(self):
        self.log.info("Listing endpoints:")
        ret = self._core_v1_api.list_endpoints_for_all_namespaces(watch=False)
        for i in ret.items:
            self.log.info("%s\t%s" % (i.metadata.namespace, i.metadata.name))

    # ----
    def create_namespace(self, namespace : str):
        self.log.info(f"Creating \"{namespace}\" namespace")

        ns = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=namespace)
        )
        try:
            #
            resp = self._core_v1_api.create_namespace(
                body=ns
            )
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create namespace \"{namespace}\"") from e

    # ----
    def delete_namespace(self, namespace: str):
        self.log.info(f"Deleting \"{namespace}\" namespace")
        try:
            #
            resp = self._core_v1_api.delete_namespace(
                name=namespace
            )
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to delete namespace \"{namespace}\"") from e

    def get_container_port_list_from_connections(self, connections:list=None):
        ret = [
            client.V1ContainerPort(
                name = 'restcmd',
                protocol = "TCP",
                container_port = 3333,
            )]
        for c in connections:
            uri = urlparse(c['uri'])
            print(uri)
            if uri.hostname != '0.0.0.0': continue

            ret += [
                client.V1ContainerPort(
                    # My sympathy for the nwmgr took yet another hit here
                    name = c['uid'].lower().replace(".", "").replace("_", "").replace("$","").replace("{", "").replace("}", "")[-15:],
                    protocol = uri.scheme.upper(),
                    container_port = uri.port,
                )]
        return ret


    def get_service_port_list_from_connections(self, connections:list=None):
        ret = [
            client.V1ServicePort(
                name = 'restcmd',
                protocol = "TCP",
                target_port = 3333,
                port = 3333,
            )]

        for c in connections:
            uri = urlparse(c['uri'])
            print(uri)
            if uri.hostname != '0.0.0.0': continue

            ret += [
                client.V1ServicePort(
                    # My sympathy for the nwmgr took yet another hit here
                    name = c['uid'].lower().replace(".", "").replace("_", "").replace("$","").replace("{", "").replace("}", "")[-15:],
                    protocol = uri.scheme.upper(),
                    target_port = uri.port,
                    port = uri.port,
                )]
        return ret

    # ----
    def create_daqapp_pod(
            self,
            name: str,
            app_label: str,
            app_boot_info:dict,
            namespace: str,
            run_as: dict = None):

        self.log.info(f"Creating \"{namespace}:{name}\" daq application  (image: \"{app_boot_info['image']}\", use_flx={app_boot_info['use_flx']}, mount_dirs={app_boot_info['mount_dirs']})")

        pod = client.V1Pod(
            # Run the pod with same user id and group id as the current user
            # Required in kind environment to create non-root files in shared folders
            metadata = client.V1ObjectMeta(
                name=name,
                labels={"app": app_label}
            ),
            spec = client.V1PodSpec(
                security_context=client.V1PodSecurityContext(
                    run_as_user=run_as['uid'],
                    run_as_group=run_as['gid'],
                ) if run_as else None,
                # List of processes
                containers=[
                    # DAQ application container
                    client.V1Container(
                        name="daq-application",
                        image=app_boot_info["image"],
                        image_pull_policy= "IfNotPresent",
                        # Environment variables
                        security_context = client.V1SecurityContext(privileged=app_boot_info['use_flx']),
                        resources = (
                            client.V1ResourceRequirements({
                                "felix.cern/flx": "2", # requesting 2 FLXs
                                "memory": "32Gi" # yes bro
                            })
                        ) if app_boot_info['use_flx'] else None,
                        env = [
                            client.V1EnvVar(
                                name=k,
                                value=str(v)
                            ) for k,v in app_boot_info['env'].items()
                        ],
                        command=['/dunedaq/run/app-entrypoint.sh'],
                        args=app_boot_info['args'],
                        ports=self.get_container_port_list_from_connections(app_boot_info['connections']),
                        volume_mounts=(
                            ([
                                client.V1VolumeMount(
                                    mount_path="/cvmfs/dunedaq.opensciencegrid.org",
                                    name="dunedaq-cvmfs",
                                    read_only=True
                            )] if self.mount_cvmfs else []) +
                            ([
                                client.V1VolumeMount(
                                    mount_path="/cvmfs/dunedaq-development.opensciencegrid.org",
                                    name="dunedaq-dev-cvmfs",
                                    read_only=True
                            )] if self.mount_cvmfs else []) +
                            ([
                                client.V1VolumeMount(
                                    mount_path="/dunedaq/pocket",
                                    name="pocket",
                                    read_only=False
                            )] if self.cluster_config.is_kind else []) +
                            ([
                                client.V1VolumeMount(
                                    mount_path="/dev",
                                    name="devfs",
                                    read_only=False
                            )] if app_boot_info['use_flx'] else []) +
                            ([
                                client.V1VolumeMount(
                                    mount_path=mount_dir,
                                    name=f"mount-dir-{i}",
                                    read_only=False
                            ) for i,mount_dir in enumerate(app_boot_info['mount_dirs']) ])
                        )
                    )
                ],
                volumes=(
                    ([
                        client.V1Volume(
                            name="dunedaq-cvmfs",
                            host_path=client.V1HostPathVolumeSource(path='/cvmfs/dunedaq.opensciencegrid.org')
                        )
                    ] if self.mount_cvmfs else []) +
                    ([
                        client.V1Volume(
                            name="dunedaq-dev-cvmfs",
                            host_path=client.V1HostPathVolumeSource(path='/cvmfs/dunedaq-development.opensciencegrid.org')
                        )
                    ] if self.mount_cvmfs else []) +
                    ([
                        client.V1Volume(
                            name="pocket",
                            host_path=client.V1HostPathVolumeSource(path='/pocket')
                        )
                    ] if self.cluster_config.is_kind else [])+
                    ([
                        client.V1Volume(
                            name="devfs",
                            host_path=client.V1HostPathVolumeSource(path='/dev')
                        )
                    ] if app_boot_info['use_flx'] else []) +
                    ([
                        client.V1Volume(
                            name=f"mount-dir-{i}",
                            host_path=client.V1HostPathVolumeSource(path=mount_dir)
                        )
                    for i,mount_dir in enumerate(app_boot_info['mount_dirs']) ])
                )
            )
        )

        self.log.debug(pod)

        # Creation of the pod in specified namespace
        try:
            #
            resp = self._core_v1_api.create_namespaced_pod (
                namespace = namespace,
                body = pod
            )
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create daqapp pod \"{namespace}:{name}\"") from e

        service = client.V1Service(
            metadata = client.V1ObjectMeta(name=name),
            spec = client.V1ServiceSpec(
                ports = self.get_service_port_list_from_connections(app_boot_info['connections']),
                selector = {"app": app_label}
            )
        )  # V1Service
        self.log.debug(service)

        try:
            resp = self._core_v1_api.create_namespaced_service(namespace, service)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create daqapp service \"{namespace}:{name}\"") from e

    # ----
    def create_nanorc_responder(self, name: str, namespace: str, ip: str, port: int):

        self.log.info(f"Creating nanorc responder service \"{namespace}:{name}\" for \"{ip}:{port}\"")

        # Creating Service object
        service = client.V1Service(
            metadata=client.V1ObjectMeta(
                name=name,
            ),
            spec=client.V1ServiceSpec(
                ports=[
                    client.V1ServicePort(
                        protocol = 'TCP',
                        target_port = port,
                        port = port,
                    )
                ],
            )
        )  # V1Service

        self.log.debug(service)
        try:
            resp = self._core_v1_api.create_namespaced_service(namespace, service)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create nanorc responder service \"{namespace}:{name}\"") from e

        self.log.info(f"Creating nanorc responder endpoint {ip}:{port}")

        # Create Endpoints Objects
        endpoints = client.V1Endpoints(
            metadata = client.V1ObjectMeta(name=name),
            subsets=[
                client.V1EndpointSubset(
                    addresses = [
                        client.V1EndpointAddress(ip=ip)
                    ],
                    ports=[
                        client.CoreV1EndpointPort(port=port)
                    ]
                )
            ]
        )
        self.log.debug(endpoints)

        try:
            self._core_v1_api.create_namespaced_endpoints(namespace, endpoints)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create nanorc responder endpoint \"{namespace}:{name}\"") from e

    """
    ---
    # Source: cvmfs-csi/templates/persistentvolumeclaim.yaml
    apiVersion: v1
    kind: PersistentVolumeClaim
    metadata:
      name: dunedaq.opensciencegrid.org
    spec:
      accessModes:
      - ReadOnlyMany
      resources:
        requests:
          storage: 1Gi
      storageClassName: dunedaq.opensciencegrid.org
    """
    def create_cvmfs_pvc(self, name: str, namespace: str):

        # Create claim
        claim = client.V1PersistentVolumeClaim(
            # Meta-data
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=namespace
            ),
            # Claim
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=['ReadOnlyMany'],
                resources=client.V1ResourceRequirements(
                        requests={'storage': '2Gi'}
                    ),
                storage_class_name=name
                )
            )

        try:
            self._core_v1_api.create_namespaced_persistent_volume_claim(namespace, claim)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create persistent volume claim \"{namespace}:{name}\"") from e

    #---
    def boot(self, boot_info, timeout):

        if self.apps:
            raise RuntimeError(
                f"ERROR: apps have already been booted {' '.join(self.apps.keys())}. Terminate them all before booting a new set."
            )

        if self.cluster_config.is_kind:
            logging.info('Resolving the kind gateway')
            import docker, ipaddress
            # Detect docker environment
            docker_client = docker.from_env()

            # Find the docker network called Kind
            try:
                kind_network = next(iter(n for n in docker_client.networks.list() if n.name == 'kind'))
            except Exception as exc:
                raise RuntimeError("Failed to identfy docker network 'kind'") from exc

            # And extract the gateway ip, which corresponds to the host
            try:
                self.gateway = next(iter(s['Gateway'] for s in kind_network.attrs['IPAM']['Config'] if isinstance(ipaddress.ip_address(s['Gateway']), ipaddress.IPv4Address)), None)
            except Exception as exc:
                raise RuntimeError("Identify the kind gateway address'") from exc
            logging.info(f"Kind network gateway: {self.gateway}")
        else:
            self.gateway = socket.gethostbyname(self.cluster_config.address)
            logging.info(f"K8s gateway: {self.gateway} ({self.cluster_config.address})")

        apps = boot_info["apps"].copy()
        env_vars = boot_info["env"]
        hosts = boot_info["hosts"]

        self.partition = boot_info['env']['DUNEDAQ_PARTITION']
        cmd_port = 3333

        # Create partition
        self.create_namespace(self.partition)
        # Create the persistent volume claim
        self.create_cvmfs_pvc('dunedaq.opensciencegrid.org', self.partition)

        run_as = {
            'uid': os.getuid(),
            'gid': os.getgid(),
        }

        for app_name, app_conf in apps.items():

            host = hosts[app_conf["host"]]
            env_formatter = {
                "APP_HOST": host,
                "DUNEDAQ_PARTITION": env_vars['DUNEDAQ_PARTITION'],
                "APP_NAME": app_name,
                "APP_PORT": cmd_port,
                "APP_WD": os.getcwd(),
            }

            exec_data = boot_info['exec'][app_conf['exec']]
            exec_vars_cp = cp.deepcopy(exec_data['env'])
            exec_vars = {}

            for k,v in exec_vars_cp.items():
                exec_vars[k]=v.format(**env_formatter)

            app_env = {}
            app_env.update(env_vars)
            app_env.update(exec_vars)

            env_formatter.update(app_env)
            app_args = [a.format(**env_formatter) for a in boot_info['exec'][app_conf['exec']]['args']]
            app_img = exec_data['image']
            app_cmd = exec_data['cmd']

            unwanted_env = ['PATH', 'LD_LIBRARY_PATH', 'CET_PLUGIN_PATH','DUNEDAQ_SHARE_PATH']
            for var in unwanted_env:
                if var in app_env:
                    del app_env[var]

            app_boot_info ={
                "env": app_env,
                "args": app_args,
                "image": app_img,
                #"cmd": app_cmd, ##ignred
                "use_flx": ("ruflx" in app_name),
                "mount_dirs": self.mount_dirs[app_name],
                "connections": self.connections[app_name],
            }

            self.log.info(json.dumps(app_boot_info, indent=2))
            app_desc = AppProcessDescriptor(app_name)
            app_desc.conf = app_conf.copy()
            app_desc.partition = self.partition
            app_desc.host = f'{app_name}.{self.partition}'
            app_desc.pod = ''
            app_desc.port = cmd_port
            app_desc.proc = K8sProcess(self, app_name, self.partition)

            k8s_name = app_name.replace("_", "-").replace(".", "")

            self.create_daqapp_pod(
                name = k8s_name, # better kwargs all this...
                app_label = k8s_name,
                app_boot_info = app_boot_info,
                namespace = self.partition,
                run_as = run_as
            )

            self.apps[app_name] = app_desc

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            total = progress.add_task("[yellow]# apps started", total=len(self.apps))
            apps_tasks = {
                a: progress.add_task(f"[blue]{a}", total=1) for a in self.apps
            }
            waiting = progress.add_task("[yellow]timeout", total=timeout)

            for _ in range(timeout):
                progress.update(waiting, advance=1)

                ready = self.check_apps()
                for a, t in apps_tasks.items():
                    if a in ready:
                        progress.update(t, completed=1)
                        self.apps[a].pod = ready[a]
                progress.update(total, completed=len(ready))
                if list(ready.keys()) == list(self.apps.keys()):
                    progress.update(waiting, visible=False)
                    break

                time.sleep(1)

        self.create_nanorc_responder(
            name = 'nanorc',
            namespace = self.partition,
            ip = self.gateway,
            port = boot_info["response_listener"]["port"])

    # ---
    def check_apps(self):
        ready = {}
        for p in self._core_v1_api.list_namespaced_pod(self.partition).items:
            for name in self.apps.keys():
                if name in p.metadata.name and p.status.phase == "Running":
                    ready[name]=p.metadata.name
        return ready

    # ---
    def terminate(self):

        timeout = 60
        if self.partition:
            self.delete_namespace(self.partition)

            for _ in track(range(timeout), description="Terminating namespace..."):

                s = self._core_v1_api.list_namespace()
                found = False
                for namespace in s.items:
                    if namespace.metadata.name == self.partition:
                        found = True
                        break
                if not found:
                    return
                time.sleep(1)

            logging.warning('Timeout expired!')


# ---
def main():

    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

    partition = 'dunedaq-0'
    pm = K8SProcessManager()
    # pm.list_pods()
    # pm.list_endpoints()
    pm.create_namespace(partition)
    pm.create_cvmfs_pvc('dunedaq.opensciencegrid.org', partition)
    pm.create_daqapp_pod('trigger', 'trg', partition, True)
    pm.create_nanorc_responder('nanorc', 'nanorc', partition, '128.141.174.0', 56789)
    # pm.list_pods()

if __name__ == '__main__':
    main()
