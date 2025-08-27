#
# Nornir-based configuration deployment for netlab
#
# This module provides an alternative to Ansible for faster configuration deployment
#

import os
import sys
import typing
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from box import Box
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

from ..utils import log
from ..nornir import AnsibleInventoryAdapter, deploy_custom_config
from ..nornir.tasks import collect_device_config


console = Console()


def print_result_summary(results: dict, start_time: datetime) -> None:
    """
    Print a summary of Nornir execution results
    """
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    # Count results
    total = len(results)
    success = sum(1 for r in results.values() if not r.failed)
    failed = total - success
    changed = sum(1 for r in results.values() if not r.failed and r.changed)
    
    # Create summary table
    table = Table(title=f"Deployment Summary (completed in {duration:.2f}s)")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    
    table.add_row("[green]Successful", str(success))
    if changed:
        table.add_row("[yellow]Changed", str(changed))
    if failed:
        table.add_row("[red]Failed", str(failed))
    table.add_row("Total", str(total))
    
    console.print(table)
    
    # Show failed hosts if any
    if failed:
        console.print("\n[red]Failed hosts:")
        for host, result in results.items():
            if result.failed:
                console.print(f"  - {host}: {result.result}")


def run_nornir_config(template: str, topology: Box, limit: typing.Optional[str] = None,
                     num_workers: int = 100, dry_run: bool = False,
                     diff: bool = True, verbose: bool = False) -> bool:
    """
    Deploy configuration using Nornir
    
    Args:
        template: Configuration template name
        topology: Netlab topology data
        limit: Comma-separated list of hosts to limit deployment
        num_workers: Number of parallel workers
        dry_run: Perform dry run without applying changes
        diff: Show configuration diff
        verbose: Verbose output
        
    Returns:
        True if successful, False otherwise
    """
    # Parse limit into host list
    limit_hosts = None
    if limit:
        limit_hosts = [h.strip() for h in limit.split(',')]
    
    # Create Nornir inventory from Ansible inventory
    console.print(f"[cyan]Loading inventory...")
    try:
        adapter = AnsibleInventoryAdapter()
        nr = adapter.create_nornir_object(limit=limit_hosts, num_workers=num_workers)
    except Exception as e:
        log.error(f"Failed to create Nornir inventory: {e}", "nornir")
        return False
    
    # Get search paths from topology
    search_paths = topology.defaults.paths.custom.dirs
    
    # Show what we're about to do
    console.print(f"\n[bold]Deploying configuration template: {template}")
    console.print(f"Target hosts: {len(nr.inventory.hosts)}")
    console.print(f"Parallel workers: {num_workers}")
    if dry_run:
        console.print("[yellow]DRY RUN - No changes will be made")
    
    # Deploy configuration with progress tracking
    start_time = datetime.now()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Deploying configurations...", total=len(nr.inventory.hosts))
        
        def deploy_with_progress(nr_task):
            """Wrapper to update progress bar"""
            result = deploy_custom_config(
                nr_task,
                template_name=template,
                search_paths=search_paths,
                commit=not dry_run,
                diff=diff
            )
            progress.update(task, advance=1)
            return result
        
        # Run deployment
        results = nr.run(task=deploy_with_progress)
    
    # Show results
    print_result_summary(results, start_time)
    
    # Show diffs if requested and available
    if diff and not dry_run:
        for host, result in results.items():
            if not result.failed and hasattr(result, 'diff') and result.diff:
                console.print(f"\n[bold]Configuration diff for {host}:")
                console.print(result.diff)
    
    # Return success/failure
    return all(not r.failed for r in results.values())


def run_nornir_initial(topology: Box, limit: typing.Optional[str] = None,
                      num_workers: int = 100, verbose: bool = False) -> bool:
    """
    Deploy initial device configuration using Nornir
    
    Args:
        topology: Netlab topology data
        limit: Comma-separated list of hosts to limit deployment
        num_workers: Number of parallel workers
        verbose: Verbose output
        
    Returns:
        True if successful, False otherwise
    """
    # Initial config is just a special case of config deployment
    return run_nornir_config(
        template='initial',
        topology=topology,
        limit=limit,
        num_workers=num_workers,
        dry_run=False,
        diff=False,  # Initial config doesn't need diff
        verbose=verbose
    )


def run_nornir_collect(topology: Box, output_dir: str = "configs",
                      limit: typing.Optional[str] = None,
                      num_workers: int = 100, verbose: bool = False) -> bool:
    """
    Collect device configurations using Nornir
    
    Args:
        topology: Netlab topology data
        output_dir: Directory to save configurations
        limit: Comma-separated list of hosts to limit collection
        num_workers: Number of parallel workers
        verbose: Verbose output
        
    Returns:
        True if successful, False otherwise
    """
    # Parse limit
    limit_hosts = None
    if limit:
        limit_hosts = [h.strip() for h in limit.split(',')]
    
    # Create output directory
    Path(output_dir).mkdir(exist_ok=True)
    
    # Create Nornir inventory
    console.print(f"[cyan]Loading inventory...")
    try:
        adapter = AnsibleInventoryAdapter()
        nr = adapter.create_nornir_object(limit=limit_hosts, num_workers=num_workers)
    except Exception as e:
        log.error(f"Failed to create Nornir inventory: {e}", "nornir")
        return False
    
    # Collect configurations
    console.print(f"\n[bold]Collecting configurations from {len(nr.inventory.hosts)} devices")
    start_time = datetime.now()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Collecting configurations...", total=len(nr.inventory.hosts))
        
        def collect_with_progress(nr_task):
            """Wrapper to update progress bar"""
            result = collect_device_config(nr_task)
            progress.update(task, advance=1)
            return result
        
        # Run collection
        results = nr.run(task=collect_with_progress)
    
    # Save configurations
    console.print("\n[cyan]Saving configurations...")
    saved = 0
    for host, result in results.items():
        if not result.failed:
            config_file = Path(output_dir) / f"{host}.cfg"
            config_file.write_text(result.result)
            saved += 1
            if verbose:
                console.print(f"  Saved {host} → {config_file}")
    
    # Show summary
    print_result_summary(results, start_time)
    console.print(f"\n[green]Saved {saved} configurations to {output_dir}/")
    
    return all(not r.failed for r in results.values())


def add_nornir_arguments(parser) -> None:
    """
    Add Nornir-specific arguments to an argument parser
    
    Args:
        parser: ArgumentParser instance
    """
    parser.add_argument(
        '--engine',
        choices=['ansible', 'nornir'],
        default='ansible',
        help='Configuration deployment engine (default: ansible)'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=100,
        help='Number of parallel workers for Nornir (default: 100)'
    )
    parser.add_argument(
        '--no-diff',
        dest='diff',
        action='store_false',
        default=True,
        help='Do not show configuration diff'
    )