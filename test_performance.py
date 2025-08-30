#!/usr/bin/env python3
"""
Test script to demonstrate performance improvements
"""

import time
import sys
import os
from pathlib import Path

# Add the workspace to Python path to use our optimized modules
sys.path.insert(0, '/workspace')

def create_large_topology(num_nodes=100, num_links_per_node=3):
    """Create a test topology file"""
    print(f"Creating test topology with {num_nodes} nodes...")
    
    topology = """# Large test topology
defaults:
  device: eos
  provider: libvirt

module: [ ospf, bgp ]

nodes:
"""
    
    # Add nodes in groups for efficiency
    for i in range(0, num_nodes, 10):
        topology += f"""
  # Spine group {i//10}
  spine_{i//10}:
    group: spines
    bgp.as: 65000
"""
        for j in range(min(10, num_nodes - i)):
            topology += f"""  
  leaf_{i+j}:
    group: leaves  
    bgp.as: {65001 + i + j}
"""
    
    topology += """
groups:
  spines:
    device: eos
    module: [ ospf, bgp ]
    role: spine
    
  leaves:
    device: eos  
    module: [ ospf, bgp ]
    role: leaf

links:
"""
    
    # Create a partial mesh topology
    for i in range(num_nodes):
        for j in range(num_links_per_node):
            target = (i + j + 1) % num_nodes
            if i < target:  # Avoid duplicate links
                node1 = f"spine_{i//10}" if i % 10 == 0 else f"leaf_{i}"
                node2 = f"spine_{target//10}" if target % 10 == 0 else f"leaf_{target}"
                topology += f"  - {node1} - {node2}\n"
    
    return topology

def test_standard_performance(topology_file):
    """Test standard netlab create"""
    print("\nTesting STANDARD netlab create...")
    start = time.time()
    
    # Use the existing netlab
    os.system(f"netlab create {topology_file} > /dev/null 2>&1")
    
    elapsed = time.time() - start
    print(f"Standard mode completed in {elapsed:.2f} seconds")
    return elapsed

def test_optimized_performance(topology_file):
    """Test optimized netlab create"""
    print("\nTesting OPTIMIZED netlab create...")
    
    # Import our optimized modules
    from netsim.cli import create_optimized
    from netsim.utils import read_optimized
    
    # Clear cache for fair comparison
    read_optimized.clear_cache()
    
    start = time.time()
    
    # Run with optimizations
    args = [
        '--fast',      # Skip non-essential validation
        '--parallel',  # Use parallel processing
        '--cache',     # Use caching
        topology_file
    ]
    
    try:
        create_optimized.run(args)
    except SystemExit:
        pass  # Normal exit
    
    elapsed = time.time() - start
    print(f"Optimized mode completed in {elapsed:.2f} seconds")
    
    # Show cache stats
    stats = read_optimized.get_cache_stats()
    print(f"Cache stats: {stats['performance']}")
    
    return elapsed

def test_cached_performance(topology_file):
    """Test performance with warm cache"""
    print("\nTesting CACHED netlab create (2nd run)...")
    
    from netsim.cli import create_optimized
    
    start = time.time()
    
    args = [
        '--fast',
        '--parallel', 
        '--cache',
        topology_file
    ]
    
    try:
        create_optimized.run(args)
    except SystemExit:
        pass
    
    elapsed = time.time() - start
    print(f"Cached mode completed in {elapsed:.2f} seconds")
    return elapsed

def cleanup():
    """Remove generated files"""
    for pattern in ['test_topology_*.yml', 'netlab.*', '*.retry', 'hosts.yml', 
                   'ansible.cfg', 'Vagrantfile', 'clab.yml']:
        for f in Path('.').glob(pattern):
            f.unlink()

def main():
    print("=" * 60)
    print("Netlab Performance Improvement Demonstration")
    print("=" * 60)
    
    # Test different sizes
    test_sizes = [50, 100, 200]
    
    for size in test_sizes:
        print(f"\n{'='*60}")
        print(f"Testing with {size} nodes")
        print(f"{'='*60}")
        
        # Create test topology
        topology = create_large_topology(size)
        topology_file = f'test_topology_{size}.yml'
        
        with open(topology_file, 'w') as f:
            f.write(topology)
        
        # Run tests
        results = {}
        
        # Standard mode
        cleanup()
        results['standard'] = test_standard_performance(topology_file)
        
        # Optimized mode (cold cache)
        cleanup()
        results['optimized'] = test_optimized_performance(topology_file)
        
        # Cached mode (warm cache)
        results['cached'] = test_cached_performance(topology_file)
        
        # Calculate improvements
        speedup_cold = results['standard'] / results['optimized']
        speedup_warm = results['standard'] / results['cached']
        
        print(f"\n{'='*60}")
        print(f"RESULTS for {size} nodes:")
        print(f"  Standard:  {results['standard']:.2f}s")
        print(f"  Optimized: {results['optimized']:.2f}s ({speedup_cold:.1f}x faster)")
        print(f"  Cached:    {results['cached']:.2f}s ({speedup_warm:.1f}x faster)")
        print(f"{'='*60}")
        
        # Cleanup
        cleanup()
        Path(topology_file).unlink()
    
    print("\n" + "="*60)
    print("Performance test completed!")
    print("="*60)
    
    print("\nTo use these optimizations in your workflow:")
    print("1. Install: python performance_patch.py --install")
    print("2. Use: netlab create --fast --parallel your_topology.yml")
    print("3. Enjoy the speed! 🚀")

if __name__ == '__main__':
    main()