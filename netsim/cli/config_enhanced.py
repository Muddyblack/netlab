#
# Enhanced netlab config command with Nornir support
#
# Deploy custom configuration template to network devices using Ansible or Nornir
#
import argparse
import glob
import os
import sys
import typing

from box import Box

from ..utils import files as _files
from ..utils import log
from . import ansible, load_snapshot, parser_add_verbose, parser_lab_location
from .external_commands import set_ansible_flags
from .nornir_config import run_nornir_config, add_nornir_arguments


#
# CLI parser for 'netlab config' command with Nornir support
#
def custom_config_parse(args: typing.List[str]) -> typing.Tuple[argparse.Namespace, typing.List[str]]:
  parser = argparse.ArgumentParser(
    prog='netlab config',
    description='Deploy custom configuration template',
    epilog='Additional arguments are passed to the deployment engine')
  parser.add_argument(
    '-r','--reload',
    dest='reload',
    action='store_true',
    help='Reload saved device configurations')
  parser.add_argument(
    dest='template', action='store',
    help='Configuration template or a directory with templates')
  parser.add_argument(
    '--dry-run',
    action='store_true',
    help='Perform a dry run without applying changes (Nornir only)')
  parser.add_argument(
    '--limit',
    dest='limit',
    help='Limit deployment to specific hosts (comma-separated)')
  
  # Add Nornir-specific arguments
  add_nornir_arguments(parser)
  
  parser_add_verbose(parser)
  parser_lab_location(parser,instance=True,action='configure')

  return parser.parse_known_args(args)


def path_exists(c_path: str) -> bool:
  return bool(
      os.path.isdir(c_path) or
      os.path.exists(c_path+'.j2') or
      glob.glob(c_path+'.*.j2'))


def template_sanity_check(template: str, topology: Box, verbose: bool) -> bool:
  if template.startswith("/"):                    # Absolute path specified as the template name?
    return path_exists(template)

  for path in topology.defaults.paths.custom.dirs:
    c_path = path+"/"+template
    if verbose:
      print(f"Looking for {c_path}")
    if path_exists(c_path):
      return True

  return False


def run(cli_args: typing.List[str]) -> None:
  (args,rest) = custom_config_parse(cli_args)
  log.set_logging_flags(args)

  topology = load_snapshot(args)

  # Validate template
  if args.template != '-':
    if args.template[0] in "~/.":                 # Change directory references into absolute path
      args.template = str(_files.absolute_path(args.template))

    if not template_sanity_check(args.template, topology, args.verbose):
      log.fatal(f'Cannot find specified Jinja2 template or configuration directory {args.template}', 'config')

  # Check which engine to use
  if args.engine == 'nornir':
    # Use Nornir for deployment
    if args.reload:
      log.error("Configuration reload is not yet supported with Nornir engine", "config")
      sys.exit(1)
    
    # Check for Nornir availability
    try:
      import nornir
      import nornir_napalm
      import nornir_scrapli
      import nornir_utils
    except ImportError as e:
      log.error(
        f"Nornir dependencies not installed: {e}\n"
        "Install with: pip install nornir nornir-napalm nornir-scrapli nornir-utils",
        "config"
      )
      sys.exit(1)
    
    # Run Nornir deployment
    success = run_nornir_config(
      template=args.template,
      topology=topology,
      limit=args.limit,
      num_workers=args.workers,
      dry_run=args.dry_run,
      diff=args.diff,
      verbose=args.verbose
    )
    
    if not success:
      sys.exit(1)
  else:
    # Use Ansible for deployment (existing behavior)
    set_ansible_flags(rest)
    
    # Add limit if specified
    if args.limit:
      rest = ['--limit', args.limit] + rest
    
    if args.template != '-':
      rest = ['-e', 'config='+args.template] + rest
    
    if args.verbose:
      print(f'Ansible playbook args: {rest}')
    
    if args.reload:
      ansible.playbook('reload-config.ansible', rest)
    else:
      ansible.playbook('config.ansible', rest)

  log.repeat_warnings('netlab config')