#!/usr/bin/env python3
"""
Performance patch for netlab - integrates optimized modules

This script patches the existing netlab installation to use optimized versions
of critical modules for better performance with large topologies.

Usage:
    python performance_patch.py --install    # Install optimizations
    python performance_patch.py --uninstall  # Remove optimizations
    python performance_patch.py --benchmark  # Run performance tests
"""

import sys
import os
import shutil
import argparse
import time
from pathlib import Path

def install_optimizations():
    """Install optimized modules"""
    print("Installing netlab performance optimizations...")
    
    # Find netlab installation
    import netsim
    netlab_path = Path(netsim.__file__).parent
    
    # Backup original files
    backup_dir = netlab_path / '.backup'
    backup_dir.mkdir(exist_ok=True)
    
    files_to_patch = [
        ('utils/read.py', 'utils/read_optimized.py'),
        ('augment/main.py', 'augment/main_optimized.py'),
        ('cli/create.py', 'cli/create_optimized.py')
    ]
    
    for orig, opt in files_to_patch:
        orig_path = netlab_path / orig
        opt_path = Path(__file__).parent / 'netsim' / opt
        backup_path = backup_dir / orig.replace('/', '_')
        
        if orig_path.exists():
            # Backup original
            shutil.copy2(orig_path, backup_path)
            print(f"  Backed up {orig} to {backup_path}")
            
            # Install optimized version
            if opt_path.exists():
                shutil.copy2(opt_path, orig_path)
                print(f"  Installed optimized {orig}")
            else:
                # If optimized file not found, patch the import
                patch_imports(orig_path, opt)
    
    # Add performance monitoring
    add_performance_wrapper()
    
    print("\nOptimizations installed successfully!")
    print("Use 'netlab create --fast --parallel' for best performance")

def patch_imports(file_path: Path, optimized_module: str):
    """Patch imports to use optimized modules"""
    content = file_path.read_text()
    
    # Add import for optimized module at the top
    module_name = optimized_module.replace('.py', '').replace('/', '.')
    import_line = f"from . import {module_name.split('.')[-1]}\n"
    
    # Replace key functions with optimized versions
    replacements = {
        'read.py': [
            ('def load(', f'def load_original('),
            ('def read_yaml(', 'def read_yaml_original('),
            # Add redirect to optimized version
            ('def load_original(', f'load = {module_name.split(".")[-1]}.load_optimized\ndef load_original(')
        ],
        'main.py': [
            ('def transform(', 'def transform_original('),
            ('def transform_original(', f'transform = {module_name.split(".")[-1]}.transform_optimized\ndef transform_original(')
        ],
        'create.py': [
            ('def run(', 'def run_original('),
            ('def run_original(', f'run = {module_name.split(".")[-1]}.run_optimized\ndef run_original(')
        ]
    }
    
    file_type = file_path.name
    if file_type in replacements:
        for old, new in replacements[file_type]:
            content = content.replace(old, new)
    
    # Write patched content
    file_path.write_text(import_line + content)

def add_performance_wrapper():
    """Add performance monitoring wrapper"""
    wrapper_code = '''
# Performance monitoring wrapper
import time
import functools

def performance_monitor(func):
    """Monitor performance of key functions"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        
        if elapsed > 1.0:  # Log slow operations
            import sys
            print(f"[PERF] {func.__name__} took {elapsed:.2f}s", file=sys.stderr)
        
        return result
    return wrapper

# Auto-patch slow functions
import netsim.augment.main
import netsim.utils.read

for module in [netsim.augment.main, netsim.utils.read]:
    for name in dir(module):
        if name.startswith('_'):
            continue
        attr = getattr(module, name)
        if callable(attr) and hasattr(attr, '__module__'):
            if attr.__module__ == module.__name__:
                setattr(module, name, performance_monitor(attr))
'''
    
    import netsim
    wrapper_path = Path(netsim.__file__).parent / '__perf_wrapper__.py'
    wrapper_path.write_text(wrapper_code)

def uninstall_optimizations():
    """Remove optimizations and restore originals"""
    print("Removing netlab performance optimizations...")
    
    import netsim
    netlab_path = Path(netsim.__file__).parent
    backup_dir = netlab_path / '.backup'
    
    if not backup_dir.exists():
        print("No backup found. Optimizations may not be installed.")
        return
    
    # Restore original files
    for backup_file in backup_dir.glob('*'):
        orig_path = netlab_path / backup_file.name.replace('_', '/')
        if backup_file.exists():
            shutil.copy2(backup_file, orig_path)
            print(f"  Restored {orig_path}")
    
    # Remove backup directory
    shutil.rmtree(backup_dir)
    
    # Remove performance wrapper
    wrapper_path = netlab_path / '__perf_wrapper__.py'
    if wrapper_path.exists():
        wrapper_path.unlink()
    
    print("\nOptimizations removed successfully!")

def run_benchmark():
    """Run performance benchmark"""
    print("Running netlab performance benchmark...")
    
    # Create test topologies of different sizes
    test_sizes = [10, 50, 100, 200]
    results = {}
    
    for size in test_sizes:
        print(f"\nTesting with {size} nodes...")
        
        # Generate test topology
        topology = generate_test_topology(size)
        test_file = f'test_topology_{size}.yml'
        
        with open(test_file, 'w') as f:
            f.write(topology)
        
        # Run with standard mode
        start = time.time()
        os.system(f'netlab create --quiet {test_file} >/dev/null 2>&1')
        standard_time = time.time() - start
        
        # Run with optimized mode
        start = time.time()
        os.system(f'netlab create --quiet --fast --parallel {test_file} >/dev/null 2>&1')
        optimized_time = time.time() - start
        
        results[size] = {
            'standard': standard_time,
            'optimized': optimized_time,
            'speedup': standard_time / optimized_time if optimized_time > 0 else 0
        }
        
        # Cleanup
        os.unlink(test_file)
        for f in Path('.').glob('netlab.*'):
            f.unlink()
    
    # Display results
    print("\nBenchmark Results:")
    print("Nodes | Standard | Optimized | Speedup")
    print("------|----------|-----------|--------")
    for size, result in results.items():
        print(f"{size:5d} | {result['standard']:8.2f}s | {result['optimized']:9.2f}s | {result['speedup']:6.1f}x")

def generate_test_topology(num_nodes: int) -> str:
    """Generate a test topology with specified number of nodes"""
    topology = f"""# Test topology with {num_nodes} nodes
defaults:
  device: eos

nodes:
"""
    
    for i in range(num_nodes):
        topology += f"  node{i}: {{}}\n"
    
    topology += "\nlinks:\n"
    
    # Create a ring topology
    for i in range(num_nodes):
        next_node = (i + 1) % num_nodes
        topology += f"  - node{i} - node{next_node}\n"
    
    return topology

def main():
    parser = argparse.ArgumentParser(description="Netlab performance optimization patch")
    parser.add_argument('--install', action='store_true', help='Install optimizations')
    parser.add_argument('--uninstall', action='store_true', help='Remove optimizations')
    parser.add_argument('--benchmark', action='store_true', help='Run performance benchmark')
    
    args = parser.parse_args()
    
    if args.install:
        install_optimizations()
    elif args.uninstall:
        uninstall_optimizations()
    elif args.benchmark:
        run_benchmark()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()