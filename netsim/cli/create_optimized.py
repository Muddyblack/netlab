#
# Optimized netlab create command with performance improvements
#
import argparse
import os
import sys
import time
import typing
from pathlib import Path

from box import Box

from .. import augment
from ..outputs import _TopologyOutput
from ..utils import log, strings, read_optimized
from . import common_parse_args, error_and_exit, lab_status_log, topology_parse_args

# Import optimized modules
from ..augment import main_optimized

def create_topology_parse_optimized(args: typing.List[str]) -> argparse.Namespace:
    """Parse arguments with performance options"""
    parents = [common_parse_args(True), topology_parse_args()]
    
    parser = argparse.ArgumentParser(
        parents=parents,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        prog="netlab create",
        description="Create provider- and automation configuration files (optimized version)")
    
    # Performance options
    perf_group = parser.add_argument_group('performance options')
    perf_group.add_argument(
        '--fast', dest='fast_mode', action='store_true',
        help='Enable fast mode (skip non-essential validation)')
    perf_group.add_argument(
        '--parallel', dest='parallel', action='store_true', default=True,
        help='Enable parallel processing (default: True)')
    perf_group.add_argument(
        '--no-parallel', dest='parallel', action='store_false',
        help='Disable parallel processing')
    perf_group.add_argument(
        '--cache', dest='use_cache', action='store_true', default=True,
        help='Use topology cache (default: True)')
    perf_group.add_argument(
        '--no-cache', dest='use_cache', action='store_false',
        help='Disable topology cache')
    perf_group.add_argument(
        '--clear-cache', dest='clear_cache', action='store_true',
        help='Clear topology cache before running')
    perf_group.add_argument(
        '--cache-stats', dest='show_cache_stats', action='store_true',
        help='Show cache statistics')
    
    # Original arguments
    parser.add_argument('--unlock', dest='unlock', action='store_true',
                    help=argparse.SUPPRESS)
    parser.add_argument(
        dest='topology', action='store', nargs='?',
        default='topology.yml',
        help='Topology file (default: topology.yml)')
    parser.add_argument(
        '-o','--output', dest='output', action='append',
        help='Output format(s): format:option=filename')
    parser.add_argument(
        '--devices', dest='devices', action='store_true',
        help='Create provider configuration file and netlab-devices.yml')
    
    return parser.parse_args(args)

def load_topology_optimized(args: argparse.Namespace) -> Box:
    """Load topology with optimizations"""
    log.set_logging_flags(args)
    
    # Handle cache operations
    if hasattr(args, 'clear_cache') and args.clear_cache:
        read_optimized.clear_cache()
        if not args.topology:
            print("Cache cleared successfully")
            sys.exit(0)
    
    if hasattr(args, 'show_cache_stats') and args.show_cache_stats:
        stats = read_optimized.get_cache_stats()
        print(f"Cache statistics:")
        print(f"  Directory: {stats['cache_dir']}")
        print(f"  Files: {stats['num_files']}")
        print(f"  Size: {stats['total_size_mb']:.2f} MB")
        print(f"  Performance: {stats['performance']}")
        if not args.topology:
            sys.exit(0)
    
    # Determine if we should use optimizations
    use_cache = getattr(args, 'use_cache', True)
    fast_mode = getattr(args, 'fast_mode', False)
    parallel = getattr(args, 'parallel', True)
    
    # Show mode information
    if not log.QUIET:
        modes = []
        if use_cache:
            modes.append("cache")
        if fast_mode:
            modes.append("fast")
        if parallel:
            modes.append("parallel")
        if modes:
            print(f"Running in {', '.join(modes)} mode")
    
    # Load topology with optimizations
    start_time = time.time()
    
    relative_name = 'test' in args and args.test and 'errors' in args.test
    
    # Use optimized loader if cache is enabled
    if use_cache:
        topology = read_optimized.load_optimized(
            args.topology,
            user_defaults=args.defaults,
            relative_topo_name=relative_name,
            skip_validation=fast_mode,
            parallel=parallel
        )
    else:
        # Fall back to original loader
        from ..utils import read as _read
        topology = _read.load(
            args.topology,
            args.defaults,
            relative_topo_name=relative_name
        )
    
    # Add CLI arguments
    if args.settings or args.device or args.provider or args.plugin:
        topology.nodes = augment.nodes.create_node_dict(topology.nodes)
        from ..utils import read as _read
        _read.add_cli_args(topology, args)
    
    # Store performance settings in topology
    topology._performance = Box({
        'fast_mode': fast_mode,
        'parallel': parallel,
        'load_time': time.time() - start_time
    })
    
    log.exit_on_error()
    return topology

def run_optimized(cli_args: typing.List[str]) -> Box:
    """Optimized create command"""
    args = create_topology_parse_optimized(cli_args)
    
    if not 'output' in args:
        args.output = None
    if not 'devices' in args:
        args.devices = None
    
    # Handle URL topologies
    if '://' in args.topology:
        from .create import http_fetch_content
        args.topology = http_fetch_content(args.topology, args)
    
    # Default outputs
    if not args.output:
        args.output = ['provider','yaml=netlab.snapshot.yml','tools']
        args.output.append('devices' if args.devices else 'ansible:dirs')
    elif args.devices:
        log.error('--output and --devices flags are mutually exclusive', log.IncorrectValue, 'create')
    
    # Check topology file
    tpath = Path(args.topology)
    if not tpath.exists():
        log.fatal(f'Topology file {args.topology} does not exist', module='create')
    if not tpath.is_file():
        log.fatal(f'The specified lab topology ({args.topology}) is not a file', module='create')
    
    # Load topology with optimizations
    print(f"Loading topology: {args.topology}")
    topology = load_topology_optimized(args)
    
    # Transform with optimizations
    transform_start = time.time()
    
    # Use optimized transformation if available
    if hasattr(topology, '_performance') and topology._performance.get('parallel', True):
        main_optimized.transform(topology)
    else:
        augment.main.transform(topology)
    
    transform_time = time.time() - transform_start
    
    log.exit_on_error()
    
    # Handle unlock
    if args.unlock and os.path.exists('netlab.lock'):
        strings.print_colored_text("WARNING: ", "bright_red", stderr=True)
        print("removing netlab.lock file, you're on your own", file=sys.stderr)
        os.remove('netlab.lock')
        lab_status_log(topology, 'Configuration files have been recreated')
    
    # Process plugins
    for p_name in topology.defaults.netlab.create.get('output', []):
        plugin = augment.plugin.load_plugin(p_name, topology)
        if plugin:
            augment.plugin.execute_plugin_hook('output', plugin, topology)
    
    # Generate outputs
    output_start = time.time()
    for output_format in args.output:
        output_module = _TopologyOutput.load(
            output_format,
            topology.defaults.outputs[output_format.split(':')[0]]
        )
        if output_module:
            output_module.write(topology)
            log.exit_on_error()
        else:
            log.error('Unknown output format %s' % output_format, log.IncorrectValue, 'create')
    
    output_time = time.time() - output_start
    
    # Report performance summary
    if not log.QUIET and hasattr(topology, '_performance'):
        total_time = time.time() - transform_start + topology._performance.load_time
        if total_time > 2:
            print(f"\nPerformance Summary:")
            print(f"  Load time: {topology._performance.load_time:.2f}s")
            print(f"  Transform time: {transform_time:.2f}s")
            print(f"  Output time: {output_time:.2f}s")
            print(f"  Total time: {total_time:.2f}s")
            
            # Compare with expected baseline
            node_count = len(topology.get('nodes', {}))
            if node_count > 0:
                time_per_node = total_time / node_count
                print(f"  Time per node: {time_per_node:.3f}s")
                if time_per_node > 0.1:
                    print("  Note: Performance can be improved with --fast mode")
    
    return topology

# Make it available as 'run' for compatibility
run = run_optimized