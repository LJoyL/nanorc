"""
Command Line Interface for NanoRC
"""
import os
import sh
import sys
import time
import json
import cmd
import click
import click_shell
import os.path
import os
import logging
import importlib.resources as resources
import threading
import socket

from . import __version__
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.traceback import Traceback


from nanorc.core import NanoRC
from nanorc.runmgr import DBRunNumberManager
from nanorc.cfgsvr import DBConfigSaver
from nanorc.credmgr import credentials
from nanorc.rest import RestApi, NanoWebContext, rc_context
from . import confdata
import nanorc.argval as argval

from nanorc.common_commands import add_common_cmds, add_custom_cmds, accept_timeout, accept_wait, check_rc, execute_cmd_sequence
from nanorc.cli import CONTEXT_SETTINGS, loglevels, updateLogLevel
from nanorc.nano_context import NanoContext

# ------------------------------------------------------------------------------
@click_shell.shell(prompt='anonymous@timingrc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__)
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default='INFO', help='Set the log level')
@click.option('--log-path', type=click.Path(exists=True), default=os.getcwd(), help='Where the logs should go (on localhost of applications)')
@accept_timeout(60)
@click.option('--cfg-dumpdir', type=click.Path(), default="./", help='Path where the config gets copied on start')
@click.option('--kerberos/--no-kerberos', default=True, help='Whether you want to use kerberos for communicating between processes')
@click.option('--partition-number', type=int, default=0, help='Which partition number to run', callback=argval.validate_partition_number)
@click.option('--web/--no-web', is_flag=True, default=False, help='whether to spawn webui')
@click.option('--tui/--no-tui', is_flag=True, default=False, help='whether to use TUI')
@click.option('--pm', type=str, default="ssh://", help='Process manager, can be: ssh://, kind://, or k8s://np04-srv-015:31000, for example', callback=argval.validate_pm)
@click.argument('cfg_dir', type=str, callback=argval.validate_conf)
@click.argument('partition-label', type=str, callback=argval.validate_partition)
@click.pass_obj
@click.pass_context
def timingcli(ctx, obj, traceback, pm, loglevel, log_path, cfg_dumpdir, kerberos, timeout, partition_number, partition_label, web, tui, cfg_dir):
    obj.print_traceback = traceback
    credentials.user = 'user'
    ctx.command.shell.prompt = f"{credentials.user}@timingrc> "
    grid = Table(title='Shonky TimingNanoRC', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky nano RC to control DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row(f"Use it with care, {credentials.user}!")

    if not tui:
        obj.console.print(Panel.fit(grid))

    port_offset = 300 + partition_number * 500
    rest_port = 5005 + partition_number
    webui_port = 5015 + partition_number

    if loglevel:
        updateLogLevel(loglevel)

    rest_thread  = threading.Thread()
    webui_thread = threading.Thread()
    if web and tui:
        raise RuntimeError("cant have TUI and GUI at the same time")
    try:
        rc = NanoRC(
            console = obj.console,
            partition_label = partition_label,
            fsm_cfg = "timing",
            top_cfg = cfg_dir,
            run_num_mgr = None,
            run_registry = None,
            logbook_type = None,
            timeout = timeout,
            pm = pm,
            use_kerb = kerberos,
            port_offset = port_offset
        )

        rc.log_path = os.path.abspath(log_path)
        add_custom_cmds(ctx.command, rc.execute_custom_command, rc.custom_cmd)
        if web or tui:
            host = socket.gethostname()

            rc_context.obj = obj
            rc_context.console = obj.console
            rc_context.top_json = cfg_dir
            rc_context.rc = rc
            rc_context.commands = ctx.command.commands
            rc_context.ctx = ctx

            obj.console.log(f"Starting up RESTAPI on {host}:{rest_port}")
            rest = RestApi(rc_context, host, rest_port)
            rest_thread = threading.Thread(target=rest.run, name="NanoRC_REST_API")
            rest_thread.start()
            obj.console.log(f"Started RESTAPI")

            if web:
                webui_thread = None
                obj.console.log(f'Starting up Web UI on {host}:{webui_port}')
                webui = WebServer(host, webui_port, host, rest_port)
                webui_thread = threading.Thread(target=webui.run, name='NanoRC_WebUI')
                webui_thread.start()
                obj.console.log(f"")
                obj.console.log(f"")
                obj.console.log(f"")
                obj.console.log(f"")
                grid = Table(title='Web NanoRC', show_header=False, show_edge=False)
                grid.add_column()
                grid.add_row(f"Started Web UI, you can now connect to: [blue]{host}:{webui_port}[/blue],")
                if 'np04' in host:
                    grid.add_row(f"You probably need to set up a SOCKS proxy to lxplus:")
                    grid.add_row("[blue]ssh -N -D 8080 your_cern_uname@lxtunnel.cern.ch[/blue] # on a different terminal window on your machine")
                    grid.add_row(f'Make sure you set up browser SOCKS proxy with port 8080 too,')
                    grid.add_row('on Chrome, \'Hotplate localhost SOCKS proxy setup\' works well).')
                grid.add_row()
                grid.add_row(f'[red]To stop this, ctrl-c [/red][bold red]twice[/bold red] (that will kill the REST and WebUI threads).')
                obj.console.print(Panel.fit(grid))
                obj.console.log(f"")
                obj.console.log(f"")
                obj.console.log(f"")
                obj.console.log(f"")

    except Exception as e:
        logging.getLogger("cli").exception("Failed to build NanoRC")
        raise click.Abort()

    def cleanup_rc():
        rc.quit()
        if rc.topnode.state != 'none': logging.getLogger("cli").warning("NanoRC context cleanup: Terminating RC before exiting")
        rc.abort(timeout=120)
        if rc.return_code:
            ctx.exit(rc.return_code)

    ctx.call_on_close(cleanup_rc)
    obj.rc = rc
    obj.shell = ctx.command
    rc.ls(False)

    if web:
        rest_thread.join()
        webui_thread.join()

    if tui:
        from .tui import NanoRCTUI
        tui = NanoRCTUI(host=host, rest_port=rest_port, timeout=rc.timeout, banner=Panel.fit(grid))
        tui.run()
        cleanup_rc()
        ctx.exit(rc.return_code)


from nanorc.common_commands import status, boot, conf, scrap, wait, terminate, start_shell, stop_run, shutdown
timingcli.add_command(status, 'status')
timingcli.add_command(boot, 'boot')
timingcli.add_command(conf, 'conf')
timingcli.add_command(scrap, 'scrap')
timingcli.add_command(wait, 'wait')
timingcli.add_command(terminate, 'terminate')
timingcli.add_command(start_shell, 'shell')
timingcli.add_command(stop_run, 'stop_run')
timingcli.add_command(shutdown, 'shutdown')

@timingcli.command('start')
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def start(ctx, obj, timeout:int):
    obj.rc.start(disable_data_storage=True, run_type="TEST", timeout=timeout, trigger_rate=None, message="")
    check_rc(ctx,obj.rc)
    obj.rc.status()

@timingcli.command('start_run')
@accept_timeout(None)
@accept_wait()
@click.pass_obj
@click.pass_context
def start_run(ctx, obj, wait:int, timeout):

    execute_cmd_sequence(
        ctx = ctx,
        rc = obj.rc,
        command = 'start_run',
        wait = wait,
        force = False,
        cmd_args = {
            'node_path':None,
            'disable_data_storage':True,
            'run_type':"TEST",
            'timeout':timeout,
            'trigger_rate':None,
            'message':""
        }
    )


@timingcli.command('stop')
@accept_timeout(None)
@click.option('--force', default=False, is_flag=True)
@click.pass_obj
@click.pass_context
def start(ctx, obj, timeout:int, force):
    obj.rc.stop(timeout=timeout, force=force)
    check_rc(ctx,obj.rc)
    obj.rc.status()


def main():
    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

    console = Console()
    credentials.console = console # some uglyness right here
    obj = NanoContext(console)

    try:
        timingcli(obj=obj, show_default=True)
    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        if not obj.print_traceback:
            console.log(e)
        else:
            console.print_exception()

if __name__ == '__main__':
    main()
