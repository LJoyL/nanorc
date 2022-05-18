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

from . import __version__
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.traceback import Traceback
from rich.progress import *


from nanorc.core import NanoRC
from nanorc.runmgr import DBRunNumberManager
from nanorc.cfgsvr import DBConfigSaver
from nanorc.credmgr import credentials
from . import confdata

from .cli import *
# ------------------------------------------------------------------------------
@click_shell.shell(prompt='anonymous@timingrc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__)
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default='INFO', help='Set the log level')
@click.option('--log-path', type=click.Path(exists=True), default=os.getcwd(), help='Where the logs should go (on localhost of applications)')
@accept_timeout(60)
@click.option('--cfg-dumpdir', type=click.Path(), default="./", help='Path where the config gets copied on start')
@click.option('--kerberos/--no-kerberos', default=True, help='Whether you want to use kerberos for communicating between processes')
@click.option('--partition-number', type=int, default=0, help='Which partition number to run', callback=validate_partition_number)
@click.argument('cfg_dir', type=click.Path(exists=True))
@click.pass_obj
@click.pass_context
def timingcli(ctx, obj, traceback, loglevel, log_path, cfg_dumpdir, kerberos, timeout, partition_number, cfg_dir):
    obj.print_traceback = traceback
    credentials.user = 'user'
    ctx.command.shell.prompt = f"{credentials.user}@timingrc> "
    grid = Table(title='Shonky TimingNanoRC', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky nano RC to control DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row(f"Use it with care, {credentials.user}!")

    obj.console.print(Panel.fit(grid))

    port_offset = 500 + partition_number * 1_000

    if loglevel:
        updateLogLevel(loglevel)

    try:
        rc = NanoRC(
            console = obj.console,
            fsm_cfg = "timing",
            top_cfg = cfg_dir,
            run_num_mgr = None,
            run_registry = None,
            logbook_type = None,
            timeout = timeout,
            use_kerb = kerberos,
            port_offset = port_offset
        )

        rc.log_path = os.path.abspath(log_path)
        add_custom_cmds(ctx.command, rc.execute_custom_command, rc.custom_cmd)
    except Exception as e:
        logging.getLogger("cli").exception("Failed to build NanoRC")
        raise click.Abort()

    def cleanup_rc():
        if rc.topnode.state != 'none': logging.getLogger("cli").warning("NanoRC context cleanup: Terminating RC before exiting")
        rc.terminate()
        if rc.return_code:
            ctx.exit(rc.return_code)

    ctx.call_on_close(cleanup_rc)
    obj.rc = rc
    obj.shell = ctx.command
    rc.ls(False)


timingcli.add_command(status, 'status')
timingcli.add_command(boot, 'boot')
timingcli.add_command(init, 'init')
timingcli.add_command(conf, 'conf')
timingcli.add_command(scrap, 'scrap')
timingcli.add_command(wait, 'wait')
timingcli.add_command(terminate, 'terminate')
timingcli.add_command(start_shell, 'shell')

@timingcli.command('start')
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def start(ctx, obj, timeout:int):
    obj.rc.start(disable_data_storage=True, run_type="TEST", timeout=timeout)
    check_rc(ctx,obj)
    obj.rc.status()


@timingcli.command('stop')
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def start(ctx, obj, timeout:int):
    obj.rc.stop(timeout=timeout)
    check_rc(ctx,obj)
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
