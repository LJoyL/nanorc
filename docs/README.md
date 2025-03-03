# Nano RC (Not ANOther Run Control)

Poor man's Run Control for DUNE DAQ applications

If you're already familiar with nanorc and wish to troubleshoot a problem, skip to the FAQ [here](FAQ.md)

## How to run me

This tutorial will guide you through the one-host minidaq example.

This tutorial assumes you run on a linux host with /cvmfs mounted, such as lxplus at CERN.

_If you want to run with Kubernetes support, the "Kubernetes support" section is later in this document_

### Setup

First, set up a working area according to [the daq-buildtools instructions](https://dune-daq-sw.readthedocs.io/en/latest/packages/daq-buildtools/).

Information can be found in `daqconf` [wiki](https://github.com/DUNE-DAQ/daqconf/wiki), or in [here](https://dune-daq-sw.readthedocs.io/en/latest/packages/daqconf/InstructionsForCasualUsers/), following is to generate a configuration and run nanorc only.

Get the example data file (TODO: asset manager and configuration - likely to change for v4.0.0):

```bash
curl -o frames.bin -O https://cernbox.cern.ch/index.php/s/0XzhExSIMQJUsp0/download
```

Generate a hardware map, with the name `HardwareMap.txt`:
```text
# DRO_SourceID DetLink DetSlot DetCrate DetID DRO_Host DRO_Card DRO_SLR DRO_Link 
100 0 4 6 3 localhost 0 0 0
101 1 4 6 3 localhost 0 0 1
```

Generate a configuration:

```bash 
daqconf_multiru_gen fake_daq
```

Next (if you want to), you can create a file called `top_level.json` which contains:

```json
{
  "apparatus_id": "fake_daq",
  "minidaq": "fake_daq"
}
```
More lines can be added later, each corresponding to a different config. This allows several sets of apps to be run in the same nanorc instance.

Now you're ready to run.

### Running NanoRC

There are 3 nanorc commands:
 - `nanorc`: for normal development,
 - `nano04rc`: for production environment at NP04,
 - `nanotimingrc`: to run the timing global partition.

To see a list of options you can pass `nanorc` in order to control things such as the amount of information it prints and the timeouts for transitions, run `nanorc -h`. We'll skip those for now in the following demo:
```
nanorc top_level.json partition-name# or "nanorc fake_daq partition-name" if you didn't create the top_level.json

╭──────────────────────────────────────────────────────────────────────────╮
│                              Shonky NanoRC                               │
│  This is an admittedly shonky nano RC to control DUNE-DAQ applications.  │
│    Give it a command and it will do your biddings,                       │
│    but trust it and it will betray you!                                  │
│  Use it with care!                                                       │
╰──────────────────────────────────────────────────────────────────────────╯

shonky rc> 
```
To see the commands available use `help`.

```
shonky rc> help

Documented commands (type help <topic>):
========================================
boot              exclude         scrap        stop                
change_rate       expert_command  shutdown     stop_run            
conf              include         start        stop_trigger_sources
disable_triggers  ls              start_run    terminate           
drain_dataflow    message         start_shell  wait                
enable_triggers   pin_threads     status

Undocumented commands:
======================
exit  help  quit
```

`boot` will start your applications. In the case of the example, a trigger application to supply triggers, a hardware signal interface (HSI) application, a readout application and a dataflow application which receives the triggers.
```
shonky rc> boot

  # apps started ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00 0:00:02
  dataflow       ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00 0:00:02
  hsi            ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00 0:00:02
  ruemu0         ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00 0:00:01
  trigger        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00 0:00:02
                                Apps                                
┏━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ name     ┃ host      ┃ alive ┃ pings ┃ last cmd ┃ last succ. cmd ┃
┡━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ dataflow │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ hsi      │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ ruemu0   │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ trigger  │ mu2edaq13 │ True  │ True  │ None     │ None           │
└──────────┴───────────┴───────┴───────┴──────────┴────────────────┘

```

You can then send the `start_run`command to get things going. `start_run` requires a run number as argument. It also optionally takes booleans to toggle data storage (`--disable-data-storage` and `--enable-data-storage`) and an integer to control trigger separation in ticks (`--trigger-interval-ticks <num ticks>`).


The Finite State Machine (FSM) is illustrated below. It shows all the transitions available for a normal DAQ application.

![FSM](DUNE_FSM.drawio.png)

The commands produce quite verbose output so that you can see what was sent directly to the applications without digging in the logfiles.

Triggers will not be generated until after a `enable_triggers` command is issued, and then trigger records with 2 links each at a default of 1 Hz will be generated.

Use 'status' to see what's going on:

```
shonky rc> status
                                    Apps                                     
┏━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ name     ┃ host      ┃ alive ┃ pings ┃ last cmd ┃ last succ. cmd ┃
┡━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ dataflow │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ hsi      │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ ruemu0   │ mu2edaq13 │ True  │ True  │ None     │ None           │
│ trigger  │ mu2edaq13 │ True  │ True  │ None     │ None           │
└──────────┴───────────┴───────┴───────┴──────────┴────────────────┘
```

When you've seen enough use the `stop_run` or `shutdown` commands. In case you experience timeout problems booting applications or sending commands, consider changing the `hosts` values from `localhost` to the hostname of your machine. This has to do with SSH authentication.

Nanorc commands can be autocompleted with TAB, for example, TAB will autocomplete `ter` to `terminate`. Options like `--disable-data-storage` will be completed with TAB after typing `start_run --d`.

You can also control nanorc in "batch mode", e.g.:
```
run_number=999
nanorc fake_daq partition-name boot conf start_run --disable-data-storage $run_number wait 2 shutdown
```
Notice the ability to control the time via transitions from the command line via the `wait` argument. 


If you want to execute command and be dropped in a shell, you can use `start_shell`:
```
run_number=999
nanorc fake_daq partition-name boot conf start_run --disable-data-storage $run_number start_shell
```

### Viewing logs and output

Logs are kept in the working directory at the time you started nanorc, named `log_<application name>_<port>.txt`, or, if you are running `nano04rc` in `/log/` on the host in which the application is running;..

You can look at the header and the value of attributes in the hdf5 file using:

```bash
h5dump-shared -H -A swtest_run000103_0000_*.hdf5
```
(your file will be named something else, of course).

To get the TriggerRecordHeaders and FragmentHeaders:

```bash
hdf5_dump.py -p both -f swtest_run000103_0000_*.hdf5
```

## More on boot

It can be instructive to take a closer look at how we can tell nanorc to `boot` the DAQ's applications. Let's take a look at a relatively simple example file in the nanorc repo, `examples/ruemu_conf/boot.json`:
```
{
    "apps": {
        "dataflow0": {
            "exec": "daq_application_ssh",
            "host": "dataflow0",
            "port": 3338
        },
        "dfo": {
            "exec": "daq_application_ssh",
            "host": "dfo",
            "port": 3335
        },
        [...]
    },
    "env": {
        "DUNEDAQ_ERS_DEBUG_LEVEL": "getenv_ifset",
        "DUNEDAQ_ERS_ERROR": "erstrace,throttle,lstdout",
        "DUNEDAQ_ERS_FATAL": "erstrace,lstdout",
        "DUNEDAQ_ERS_INFO": "erstrace,throttle,lstdout",
        "DUNEDAQ_ERS_VERBOSITY_LEVEL": "getenv:1",
        "DUNEDAQ_ERS_WARNING": "erstrace,throttle,lstdout"
    },
    "exec": {
        "daq_application_ssh": {
            "args": [
                "--name",
                "{APP_NAME}",
                "-c",
                "{CMD_FAC}",
                "-i",
                "{INFO_SVC}",
                "--configurationService",
                "{CONF_LOC}"
            ],
            "cmd": "daq_application",
            "comment": "Application profile using PATH variables (lower start time)",
            "env": {
                "CET_PLUGIN_PATH": "getenv",
                "CMD_FAC": "rest://localhost:{APP_PORT}",
                "DETCHANNELMAPS_SHARE": "getenv",
                "DUNEDAQ_SHARE_PATH": "getenv",
                "INFO_SVC": "file://info_{APP_NAME}_{APP_PORT}.json",
                "LD_LIBRARY_PATH": "getenv",
                "PATH": "getenv",
                "TIMING_SHARE": "getenv",
                "TRACE_FILE": "getenv:/tmp/trace_buffer_{APP_HOST}_{DUNEDAQ_PARTITION}"
            }
        }
    },
    "external_connections": [],
    "hosts": {
        "dataflow0": "localhost",
        "dfo": "localhost",
        "dqm0-df": "localhost",
        "dqm0-ru": "localhost",
        "hsi": "localhost",
        "ruemu0": "localhost",
        "trigger": "localhost"
    },
    "response_listener": {
        "port": 56789
    }
}
```
...you'll notice a few features about it which are common to boot files. Looking at the highest-level keys:

* `apps` contains the definition of what applications will run, and what sockets they'll be controlled on
* `env` contains a list of environment variables which can control the applications
* `hosts` is the cheatsheet whereby `apps` maps the labels of hosts to their actual names
* `exec` defines the exact procedure by which an application will be launched
* `external_connections` is a list of external connections
* `response_listener` shows on which port of localhost nanorc should expect the responses from the applications when commands are sent.

It should be pointed out that some substitutions are made when nanorc uses a file such as this to boot the processes. Specifically:

* `"getenv"` is replaced with the actual value of the environment variable, throwing a Python exception if it is unset
* `"getenv:<default value>"` is replaced with the actual value of the environment variable if it is set, with `<default value>` used if it is unset
* `"getenv_ifset"` is replaced with the actual value of the environment variable if it is set, otherwise nanorc doesn't set this variable
* If a host is provided as `localhost` or `127.0.0.1`, the result of the Python call `socket.gethostname` is used in its place
* `{APP_NAME}` is replaced by the app key name by nanorc
* `{CMD_FAC}` and `{INFO_SVC}` are replaced by their corresponding environment value
* `{CONF_LOC}` is replaced by a path to a local directory containing the configuration data that the application must be able to see.


## How to run WebUI

To access the WebUI, add the --web option when running nanorc. When nanorc starts up, it will display a box like this :

![node](node.png)

which shows what lxplus node to connect to (in dark blue in the picture above lxplusXXXX.cern.ch).

Before you can connect, a SOCKS proxy must be set up to that node in another terminal window, using `ssh -N -D 8080 username@lxplusXXXX.cern.ch` and substituting XXXX with whatever number is shown.

Once you have set up your browser to use a SOCKS proxy, connect to the address in the browser, and you should see something like this:

![GUI](GUI.png)

From here, using nanorc is just about the same as in the terminal: 

*  transitions between FSM states can be done using the State Control Buttons, 
*  the information that nanorc outputs can be viewed by clicking the expansion triangle under "Last response from nanorc" to see the details of the response.

**Note that this information will also be shown as output to the terminal.**

## How to run the TUI

To use the TUI (Terminal User Interface), add the --tui option when running nanorc. No proxy is required in this case.

![TUI](TUI.png)

Again, using nanorc is similar to the terminal:

* Transitions between states are done with the buttons in the top right: press I on the keyboard to toggle whether optional inputs are taken.
* Logs are displayed in the bottom right, and can be searched by typing in the box above them.

## Kubernetes support

This page describes the functionality which is supported within Kubernetes in v3.1.0.

### Requirements
Before you go off and try this, you at least need to have:
* A k8s cluster running. To check that this is the case, you can head to the dashboard (on the NP04 cluster, that's [here](http://np04-srv-015:31001/#/workloads?namespace=default), after you have setup a SOCKS proxy to lxplus).
* All the nodes being able to access `/cvmfs`.
* The configuration service running in the cluster. To check that, you can head to the configuration service URL (at NP04, it's [here](http://np04-srv-015:31011/)) and making sure that you see text "DAQLing Configuration Management Service v1.0.0".
* The dunedaq images on which you want to run available from all the nodes. The simplest way to do that is to have your image on dockerhub (at NP04, we have a repository [here](np04docker.cern.ch), but at the time this is being written, on the 2nd Aug 2022, it doesn't work).

All of this is available on the NP04 cluster.

### Overview

The Kubernetes prototype process manager in nanorc knows about 2 types of DUNE DAQ applications: applications that require access to FELIX card, and other applications. Applications are booted in the order provided by `boot.json`. There is no affinity set, if the user wants to run an application on different node, he/she will have to specify during the configuration.

Applications are run in `pods` with a restart policy of never, so failing applications are not restarted.

Nanorc makes use of a set of `microservices` either outside the k8s cluster or inside, in addition to the other services running on the NP04 cluster.

#### Partitions and resource management

Partitions are supported to the same level that they are in the ssh process manager version of nanorc, that is two or more instances of nanorc may be run concurrently.

The `k8s` version implements a first version of resource management: Felix cards and data storage (?) cannot be claimed by more than one partition. Readout apps start on the hosts specified in the configuration, all other apps have anti-affinity with readout apps, so start on other hosts.

#### Microservices

The following nanorc microservices are supported and can be used inside the k8s cluster or outside.

| Service | Notes |
--- | --- |
|Run Number|Provides the run number from Oracle DB|
|Run Registry|Archives configuration data (zip) and metadata to Oracle/Postgres|
|eLisa|Interface to electronic logbook at CERN|
|Configuration|Interface to MongoDB service to provide configuration|
|Felix Plugin|Registers detected Felix cards with k8s as a custom resource|

### Known missing functionality

* The output files are written on folders that are directly mounted in the host.

* It is currently not possible to address more than one Felix card on the same host (not a problem at NP04)

### NP04 cluster

Up to date documentation on the k8s test cluster at NP04 is [here](https://twiki.cern.ch/twiki/bin/view/CENF/NP04k8s), and the node assignment is [here](https://twiki.cern.ch/twiki/bin/view/CENF/ComputerAssignments)

Current nodes list (on the 2nd Aug 2022):

| node | Purpose/notes  |
--- | --- |
| np04-srv-001 | Storage          |
| np04-srv-002 | Storage          |
| np04-srv-003 | Storage          |
| np04-srv-004 | Storage          |
| np04-srv-010 | Generic DAQ host |
| np04-srv-011 | Generic DAQ host |
| np04-srv-012 | Generic DAQ host |
| np04-srv-013 | Generic DAQ host |
| np04-srv-015 | Control plane    |
| np04-srv-016 | Generic DAQ host |
| np04-srv-025 | Generic DAQ host |
| np04-srv-026 | Felix card host  |
| np04-srv-028 | Felix card host  |
| np04-srv-029 | Felix card host  |
| np04-srv-030 | Felix card host  |

## Walkthrough to run your app on k8s at NP04:

### Getting started
Log on to the np04 cluster and follow the instructions in [here](https://twiki.cern.ch/twiki/bin/view/CENF/NP04k8s).
2 important notes:
* You **do not** need to be on `np04-srv-015` to use nanorc and K8s. But you will need to have the correct `KUBECONFIG` properly set as described in the previous link.
* You **do not** need to create your namespace. That is handled automatically by nanorc.

#### Setup the nightly/release
Using the instructions at this [link](https://dune-daq-sw.readthedocs.io/en/latest/packages/daq-buildtools/#setup-of-daq-buildtools), set up a work area or a release.

**An important point is that if you want to run K8s with custom code inside the `sourcecode` directory you will need to create a docker image yourself** (see instructions at the end of this README _How to build a `daq_application` image and distribute it_).

It is worth mentioning that the `dbt-workarea-env` command will set up `spack`, which is the DAQ build system. This makes some alterations to a low-level library in `LD_LIBRARY_PATH`, which can cause some utilities like `ssh`, `nano` and `htop` to not work (you would get a segfault when running them). To fix this, run `LD_LIBRARY_PATH=/lib64 [PROGRAM_NAME]`: this will manually reset the path to what it was before spack was set up. However, this should not be required in order to run any of the commands on this page.

#### Generate a configuration and upload it on the configuration service
Create a daqconf file as such (named `config.json` in the rest of the instructions):
```json
{
  "boot": {
    "ers_impl": "cern",
    "opmon_impl": "cern",
    "use_k8s": true,
    "image": "np04docker.cern.ch/ghcr/dune-daq/c8-spack:latest"
  }
}
```
Next, you need to generate the configuration:
```sh
daqconf_multiru_gen -c config.json daq-config
```
And upload it on the MongoDB, the first argument is the directory you have just generated with `daqconf_multiru_gen` and the second is the key in the configuration on the MongoDB, **it cannot have underscores in it** since it's accessed via HTTP requests:
```sh
upload-conf daq-config ${USER}-configuration # name it something better!
```
This will create an entry in the configuration service containing all the configuration data. In this example, it will be called `${USER}-configuration`, so you probably want to name it better.

Note that the `upload-conf` utility will fails if you have proxy.

#### Run nanorc
... **after** unsetting the proxy.
```sh
source ~np04daq/bin/web_proxy.sh -u
nanorc --pm k8s://np04-srv-015:31000 db://username-configuration partition-name
nanorc> [...]
nanorc> boot
nanorc> start_run 12345
nanorc> [...]
```

### K8s dashboard, logs and monitoring
#### K8s dashboard
Hop on http://np04-srv-015:31001/ (after setting up a web SOCKS proxy to `lxplus` if you are not physically at CERN) to check the status of the cluster. Note you will need to select the partition you fed at `boot`. You'll be able to see if the pods are running or not, and where.

#### Log on a pod
First, do 
```
$ kubectl get pods -n partition-name
NAME        READY   STATUS    RESTARTS   AGE
dataflow0   1/1     Running   0          66s
...
```
to get a list of pods corresponding to DAQ applications. This should be run from the node that hosts the control plane, which is `np04-srv-015`. (The control plane is a collection of top level components that manage the whole kubernetes cluster, including the API server and a data store that keeps track of current/desired state.)

Now do:
```
kubectl exec -n partition-name --stdin --tty dataflow0 -- /bin/bash
```
to log on the pod which runs the dataflow app. The app runs in `/dunedaq/run` (which is where the data file will be too in this particular example).

#### Logs
To get the log, open a new terminal window on `np04-srv-015`, on which k8s is already installed, and do:

```sh
$ kubectl get pods -n partition-name
```

Note: `partition-name` is given as a parameter to the `nanorc` command.
```sh
$ kubectl get pods -n partition-name
NAME        READY   STATUS    RESTARTS   AGE
dataflow0   1/1     Running   0          66s
...
```
And you can use the pod name with the `kubectl logs` command:
```sh
$ kubectl logs dataflow0 -n partition-name
```

If by any "chance" something terrible happened with your pod and it core dumped for example, the k8s may either try to restart it, or give up. You can still view the stdout/stderr logs by doing:

```sh
$ kubectl logs dataflow0 -n partition-name --previous
```

#### Monitoring and Grafana
Go to http://np04-srv-009:3000/ and select your partition on the left.

### "Feature" list:
 - `daq_applications` live in pods (not deployments), with k8s pod restart policy of "Never".
 - mounts `cvmfs` in the pod (`dunedaq` and `dunedaq-development`).
 - ... Many more to discover...
 
## How to build a `daq_application` image and distribute it
NOTE: You need to be on `np04-srv-{015,016,026}` for this to work, if you are not, setup the daqenv above from above in the usual way (the first 4 commented out instructions):
```sh
# cd dunedaq-k8s/swdir
# source dbt-env.sh
# dbt-workarea-env
# cd ..
cd pocket/images/daq_application/daq_area_cvmfs/
./build_docker_image username-image-name
```
You should change `username-image-name` to something appropriate containing your username.
If you get an error message that starts with "Got permission denied while trying to connect to the docker daemon socket", then it is likely that your account is not in the docker group (this can be checked with `groups`). You can ask to be added in #np04-sysadmin, on the DUNE slack workspace.

After that, you should be able to see your image:
```sh
docker images
REPOSITORY                 TAG          IMAGE ID       CREATED        SIZE
...
username-image-name        N22-06-27    3e53688480dc   9 hours ago    1.79GB
...
```

Next, login to the local docker image repository (you'll only ever need to do that once):
```sh
docker login np04docker.cern.ch
```
Username is `np04daq` and password is available upon request to Pierre Lasorak or Bonnie King.

You need to then push the image to the NP04 local images repo:
```sh
./harbor_push username-image-name:N22-06-27 # that nightly is obviously the nightly that used earlier to setup your daq area
```

And that's it!

### Distributing "manually" the `daq_application` image
If the instructions after `docker login` didn't work, you can always do it manually:

```sh
docker save --output username-image-name-N22-06-27.tar username-image-name:N22-06-27
```

That command will create a tar file with the image. Next, you need to `ssh` on each of the node of the cluster, `cd` where the tar file is and do:

```sh
docker load --input username-image-name-N22-06-27.tar
```

and check that docker images is correct (you can check that the size and the `IMAGE ID` are the same as the one on host you generated the image):

```sh
docker images
REPOSITORY                 TAG         IMAGE ID       CREATED        SIZE
username-image-name        N22-06-27   3e53688480dc   9 hours ago    1.79GB
...
```

## Running the Felix with Kubernetes

Clone the np04daq-configs and checkout `feature/k8s`, 

``` 
git clone ssh://git@gitlab.cern.ch:7999/dune-daq/online/np04daq-configs.git 
cd np04daq-configs 
git checkout feature/k8s 
``` 


This branch uses a special image in the configuration `(np04docker.cern.ch/dunedaq-local/k8s-v400-rc3:rc-v4.0.0-3-01)` which has Eric’s modifications to IPM. Other modifications are: 
- Removing the cern.ch postfix from the hostname 
- Setting the parameter start\_connectivity\_service to false 
- Adding a use\_k8s = true and the name of the image as described above

Run the daq-config bash script:
``` 
./recreate_np04_daq_configurations.sh 
``` 

Upload the new nanorc configuration of your choice 

``` 
upload-conf [np04_daq_APA_conf] [flx-k8s-test] 
``` 

Here are some examples of [np04\_daq\_APA\_conf]'s that you can upload: 

- `np02_coldbox_daq_100mHz_conf/` 
- `np02_coldbox_daq_268ms_conf/` 
- `np02_coldbox_daq_5Hz/` 
- `np02_coldbox_daq_conf/` 
- `np02_coldbox_daq_hma_conf/` 
- `np02_coldbox_daq_tp_conf/` 
- `np02_coldbox_flxcard_conf/` 
- `np02_coldbox_flxcard_WIB12_conf/` 
- `np02_coldbox_flxcard_WIB34_conf/` 
- `np02_coldbox_flxcard_WIB56_conf/` 
- `np02_coldbox_timing_tlu_conf/` 
- `np02_coldbox_wib_conf/` 
- `np02_coldbox_wib_pulser_conf/` 
- `np02_coldbox_wib_WIB12_conf/` 
- `np02_coldbox_wib_WIB34_conf/` 
- `np02_coldbox_wib_WIB56_conf/` 
- `np04_daq_APA1_conf/` 
- `np04_daq_APA1_tp_conf/` 
- `np04_daq_APA2_conf/` 
- `np04_daq_APA2_tp_conf/` 
- `np04_daq_APA3_conf/` 
- `np04_daq_APA4_conf/` 
- `np04_daq_conf/` 
- `np04_daq_DAPHNE_conf/` 
- `np04_daq_DAPHNE_test_conf/` 
- `np04_daq_TPC_conf/` 
- `np04_flxcard_APA1_conf/` 
- `np04_flxcard_APA2_conf/` 
- `np04_flxcard_APA3_conf/` 
- `np04_flxcard_APA4_conf/` 
- `np04_flxcard_conf/` 
- `np04_flxcard_TPC_conf/` 

For this to work you need to be able to use `kubectl` which can be is done by, 

``` 
export KUBECONFIG=/nfs/home/np04daq/np04-kubernetes/config 
```

**Remember to inform** `np04_shifterassistant` **on slack that you are taking one of the APA’s for a spin and make sure no one else is running anything on it first.** 

Now you can run the nanorc using the following command: 
```
nanorc --pm k8s://np04-srv-015:31000 db://[flx-k8s-test] [yourname-flx-k8s-test-run] 
``` 
