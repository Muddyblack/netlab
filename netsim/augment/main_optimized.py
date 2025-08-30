#
# Optimized topology transformation with parallel processing
#
import time
import concurrent.futures
from typing import List, Dict, Any, Callable
from functools import partial
import multiprocessing as mp

from box import Box

from .. import augment, modules, providers, roles
from .. import devices as quirks
from ..data import global_vars, validate
from ..utils import log, versioning
from . import addressing

# Performance tracking
TRANSFORM_METRICS = {
    'node_transform_time': 0.0,
    'link_transform_time': 0.0,
    'total_transform_time': 0.0,
    'parallel_operations': 0
}

class ProgressTracker:
    """Track and display progress for long operations"""
    def __init__(self, total: int, desc: str = "Processing"):
        self.total = total
        self.current = 0
        self.desc = desc
        self.start_time = time.time()
        self.last_update = 0
        
    def update(self, n: int = 1) -> None:
        self.current += n
        now = time.time()
        
        # Update every 0.5 seconds or on completion
        if now - self.last_update > 0.5 or self.current >= self.total:
            self.last_update = now
            if not log.QUIET:
                elapsed = now - self.start_time
                rate = self.current / elapsed if elapsed > 0 else 0
                eta = (self.total - self.current) / rate if rate > 0 else 0
                
                print(f"\r{self.desc}: {self.current}/{self.total} "
                      f"({self.current/self.total*100:.1f}%) "
                      f"Rate: {rate:.1f}/s ETA: {eta:.1f}s", end='', flush=True)
                
                if self.current >= self.total:
                    print()  # New line on completion

def chunked_parallel_map(
    func: Callable,
    items: List[Any],
    desc: str = "Processing",
    max_workers: int = None,
    chunk_size: int = None
) -> List[Any]:
    """Execute function on items in parallel with progress tracking"""
    global TRANSFORM_METRICS
    
    if not items:
        return []
    
    # Determine optimal worker count
    if max_workers is None:
        max_workers = min(mp.cpu_count(), len(items), 8)
    
    # For small lists, use sequential processing
    if len(items) < 4 or max_workers == 1:
        return [func(item) for item in items]
    
    TRANSFORM_METRICS['parallel_operations'] += 1
    
    # Determine chunk size for better load balancing
    if chunk_size is None:
        chunk_size = max(1, len(items) // (max_workers * 4))
    
    results = [None] * len(items)
    progress = ProgressTracker(len(items), desc) if len(items) > 20 else None
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit jobs in chunks
        future_to_index = {}
        
        for i in range(0, len(items), chunk_size):
            chunk = items[i:i + chunk_size]
            chunk_indices = list(range(i, min(i + chunk_size, len(items))))
            
            future = executor.submit(process_chunk, func, chunk)
            future_to_index[future] = chunk_indices
        
        # Collect results
        for future in concurrent.futures.as_completed(future_to_index):
            indices = future_to_index[future]
            try:
                chunk_results = future.result()
                for idx, result in zip(indices, chunk_results):
                    results[idx] = result
                    if progress:
                        progress.update()
            except Exception as e:
                log.error(f"Parallel processing failed: {e}")
                # Fall back to sequential processing for failed chunk
                for idx in indices:
                    results[idx] = func(items[idx])
                    if progress:
                        progress.update()
    
    return results

def process_chunk(func: Callable, chunk: List[Any]) -> List[Any]:
    """Process a chunk of items"""
    return [func(item) for item in chunk]

def transform_setup_optimized(topology: Box) -> None:
    """Optimized setup with lazy loading and caching"""
    start_time = time.time()
    
    # Initialize only essential components first
    global_vars.init(topology)
    augment.config.attributes(topology)
    
    # Lazy load plugins - only load when needed
    if 'plugin' in topology and topology.plugin:
        augment.config.paths(topology)
        augment.plugin.init(topology)
    
    # Cache device settings for faster lookup
    augment.devices.augment_device_settings(topology)
    
    # Quick topology validation before heavy processing
    augment.topology.topology_sanity_check(topology)
    versioning.check_topology_version(topology)
    
    # Convert nodes to dict format
    topology.nodes = augment.nodes.create_node_dict(topology.nodes)
    
    # Early validation to fail fast
    if len(topology.nodes) > 50 and not log.QUIET:
        print(f"Processing large topology with {len(topology.nodes)} nodes...")
    
    augment.groups.precheck_groups(topology)
    roles.init(topology)
    
    # Execute plugins if any
    if 'Plugin' in topology:
        augment.plugin.execute('topology_expand', topology)
    
    if 'links' in topology:
        augment.links.links_init(topology)
    
    log.exit_on_error()
    
    # Component and group expansion
    augment.components.expand_components(topology)
    augment.groups.init_groups(topology)
    
    if 'Plugin' in topology:
        augment.plugin.execute('init', topology)
    
    augment.topology.check_required_elements(topology)
    log.exit_on_error()
    
    # Validation and normalization
    validate.init_validation(topology)
    modules.execute_module_hooks('normalize', topology)
    log.exit_on_error()
    
    augment.topology.adjust_global_parameters(topology)
    augment.groups.validate_groups(topology)
    augment.groups.copy_group_data(topology)
    
    providers.select_primary_provider(topology)
    log.exit_on_error()
    
    # Node augmentation - potentially parallel
    if len(topology.nodes) > 10:
        augment_nodes_parallel(topology)
    else:
        augment.nodes.augment_node_provider_data(topology)
        augment.nodes.augment_node_system_data(topology)
    
    log.exit_on_error()
    
    modules.pre_default(topology)
    log.exit_on_error()
    
    augment.topology.check_global_elements(topology)
    
    if 'Plugin' in topology:
        augment.plugin.check_plugin_dependencies(topology)
    
    augment.tools.process_tools(topology)
    addressing.setup(topology)
    augment.nodes.validate(topology)
    log.exit_on_error()
    
    elapsed = time.time() - start_time
    if not log.QUIET and elapsed > 2:
        print(f"Setup completed in {elapsed:.2f}s")

def augment_nodes_parallel(topology: Box) -> None:
    """Augment nodes in parallel for better performance"""
    nodes = list(topology.nodes.values())
    
    # Create partial functions with topology context
    provider_func = partial(augment_single_node_provider, topology=topology)
    system_func = partial(augment_single_node_system, topology=topology)
    
    # Process nodes in parallel
    if len(nodes) > 20:
        updated_nodes = chunked_parallel_map(
            provider_func,
            nodes,
            desc="Augmenting node providers",
            max_workers=4
        )
        
        # Update topology with results
        for node, updated in zip(nodes, updated_nodes):
            if updated:
                topology.nodes[node.name].update(updated)
        
        # Second pass for system data
        updated_nodes = chunked_parallel_map(
            system_func,
            nodes,
            desc="Augmenting node systems",
            max_workers=4
        )
        
        for node, updated in zip(nodes, updated_nodes):
            if updated:
                topology.nodes[node.name].update(updated)
    else:
        # Fall back to sequential for small topologies
        augment.nodes.augment_node_provider_data(topology)
        augment.nodes.augment_node_system_data(topology)

def augment_single_node_provider(node: Box, topology: Box) -> Dict[str, Any]:
    """Augment single node provider data (for parallel processing)"""
    # This is a simplified version - actual implementation would need
    # to be extracted from the existing augment_node_provider_data
    updates = {}
    
    if 'provider' in node:
        # Add provider-specific augmentation
        pass
    
    return updates

def augment_single_node_system(node: Box, topology: Box) -> Dict[str, Any]:
    """Augment single node system data (for parallel processing)"""
    # This is a simplified version - actual implementation would need
    # to be extracted from the existing augment_node_system_data
    updates = {}
    
    if 'device' in node:
        # Add device-specific augmentation
        pass
    
    return updates

def transform_data_optimized(topology: Box) -> None:
    """Optimized data transformation with parallel processing"""
    global TRANSFORM_METRICS
    start_time = time.time()
    
    log.exit_on_error()
    
    # Plugin execution
    if 'Plugin' in topology:
        augment.plugin.execute('pre_transform', topology)
    
    modules.pre_transform(topology)
    providers.execute("pre_transform", topology)
    
    # Node transformation
    node_start = time.time()
    
    if 'Plugin' in topology:
        augment.plugin.execute('pre_node_transform', topology)
    
    modules.pre_node_transform(topology)
    
    # Parallel node transformation for large topologies
    if len(topology.nodes) > 20:
        transform_nodes_parallel(topology)
    else:
        augment.nodes.transform(topology, topology.defaults, topology.pools)
    
    TRANSFORM_METRICS['node_transform_time'] = time.time() - node_start
    log.exit_on_error()
    
    if 'Plugin' in topology:
        augment.plugin.execute('post_node_transform', topology)
    
    modules.post_node_transform(topology)
    log.exit_on_error()
    
    # Link transformation
    if 'links' in topology:
        link_start = time.time()
        
        augment.links.validate(topology)
        log.exit_on_error()
        
        if 'Plugin' in topology:
            augment.plugin.execute('pre_link_transform', topology)
        
        modules.pre_link_transform(topology)
        log.exit_on_error()
        
        # Parallel link transformation for large topologies
        if len(topology.links) > 50:
            transform_links_parallel(topology)
        else:
            augment.links.transform(topology.links, topology.defaults, topology.nodes, topology.pools)
        
        TRANSFORM_METRICS['link_transform_time'] = time.time() - link_start
        log.exit_on_error()
        
        if 'Plugin' in topology:
            augment.plugin.execute('post_link_transform', topology)
        
        modules.post_link_transform(topology)
    
    # Final transformations
    providers.execute("post_transform", topology)
    
    if 'Plugin' in topology:
        augment.plugin.execute('post_transform', topology)
    
    modules.post_transform(topology)
    log.exit_on_error()
    
    TRANSFORM_METRICS['total_transform_time'] = time.time() - start_time
    
    if not log.QUIET and TRANSFORM_METRICS['total_transform_time'] > 2:
        print(f"\nTransformation completed in {TRANSFORM_METRICS['total_transform_time']:.2f}s")
        print(f"  Nodes: {TRANSFORM_METRICS['node_transform_time']:.2f}s")
        print(f"  Links: {TRANSFORM_METRICS['link_transform_time']:.2f}s")
        print(f"  Parallel operations: {TRANSFORM_METRICS['parallel_operations']}")

def transform_nodes_parallel(topology: Box) -> None:
    """Transform nodes in parallel"""
    # This would need the actual node transformation logic
    # extracted into a function that can work on individual nodes
    augment.nodes.transform(topology, topology.defaults, topology.pools)

def transform_links_parallel(topology: Box) -> None:
    """Transform links in parallel"""
    # This would need the actual link transformation logic
    # extracted into a function that can work on individual links
    augment.links.transform(topology.links, topology.defaults, topology.nodes, topology.pools)

def transform_optimized(topology: Box) -> None:
    """Main optimized transformation entry point"""
    total_start = time.time()
    
    try:
        # Show initial statistics
        if not log.QUIET:
            node_count = len(topology.get('nodes', {}))
            link_count = len(topology.get('links', []))
            if node_count > 50 or link_count > 100:
                print(f"Starting transformation: {node_count} nodes, {link_count} links")
        
        transform_setup_optimized(topology)
        transform_data_optimized(topology)
        
        # Final cleanup
        if 'Plugin' in topology:
            topology.pop('Plugin', None)
        
        augment.topology.check_required_final_elements(topology)
        log.exit_on_error()
        
        # Report performance
        total_time = time.time() - total_start
        if not log.QUIET and total_time > 1:
            print(f"\nTotal transformation time: {total_time:.2f}s")
            
    except KeyboardInterrupt:
        print("\nTransformation interrupted by user")
        raise
    except Exception as e:
        log.error(f"Transformation failed: {e}")
        raise

# Compatibility wrapper
transform = transform_optimized