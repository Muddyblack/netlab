#
# Optimized topology reading with caching and parallel processing
#
import os
import hashlib
import pickle
import json
import typing
import concurrent.futures
from pathlib import Path
from functools import lru_cache
import time

import yaml
from box import Box

from . import log, files as _files
from .read import UniqueKeyLoader, USER_DEFAULTS, SYSTEM_DEFAULTS

# Global cache directory
CACHE_DIR = Path.home() / '.netlab' / 'cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Performance metrics
PERF_METRICS = {
    'yaml_reads': 0,
    'cache_hits': 0,
    'cache_misses': 0,
    'total_read_time': 0.0
}

class FastYAMLLoader(yaml.SafeLoader):
    """Faster YAML loader that skips duplicate checking for trusted files"""
    pass

def get_file_hash(filepath: str) -> str:
    """Generate hash of file content for cache validation"""
    try:
        if 'package:' in filepath:
            # For package files, use the path as hash since content is stable
            return hashlib.md5(filepath.encode()).hexdigest()
        
        path = Path(filepath)
        if path.exists():
            # Include file size and mtime for faster hashing
            stat = path.stat()
            hash_str = f"{filepath}:{stat.st_size}:{stat.st_mtime}"
            return hashlib.md5(hash_str.encode()).hexdigest()
    except:
        pass
    return hashlib.md5(filepath.encode()).hexdigest()

def get_cache_path(filepath: str, include_hash: str = None) -> Path:
    """Get cache file path for a given topology file"""
    file_hash = get_file_hash(filepath)
    if include_hash:
        file_hash = f"{file_hash}_{include_hash}"
    return CACHE_DIR / f"{file_hash}.pkl"

def save_to_cache(filepath: str, data: Box, include_hash: str = None) -> None:
    """Save processed data to cache"""
    cache_path = get_cache_path(filepath, include_hash)
    try:
        with open(cache_path, 'wb') as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as e:
        if log.debug_active('cache'):
            print(f"Failed to save cache for {filepath}: {e}")

def load_from_cache(filepath: str, include_hash: str = None) -> typing.Optional[Box]:
    """Load processed data from cache if valid"""
    global PERF_METRICS
    
    cache_path = get_cache_path(filepath, include_hash)
    if not cache_path.exists():
        PERF_METRICS['cache_misses'] += 1
        return None
    
    try:
        # Check if source file is newer than cache
        if 'package:' not in filepath:
            source_path = Path(filepath)
            if source_path.exists() and source_path.stat().st_mtime > cache_path.stat().st_mtime:
                PERF_METRICS['cache_misses'] += 1
                return None
        
        with open(cache_path, 'rb') as f:
            data = pickle.load(f)
            PERF_METRICS['cache_hits'] += 1
            return Box(data)
    except Exception as e:
        if log.debug_active('cache'):
            print(f"Failed to load cache for {filepath}: {e}")
        PERF_METRICS['cache_misses'] += 1
        return None

@lru_cache(maxsize=128)
def read_yaml_fast(
    filename: typing.Optional[str] = None, 
    string: typing.Optional[str] = None,
    skip_validation: bool = False
) -> typing.Optional[Box]:
    """Optimized YAML reading with caching"""
    global PERF_METRICS
    start_time = time.time()
    
    try:
        # Try cache first for files
        if filename and not string:
            cached = load_from_cache(filename)
            if cached is not None:
                return cached
        
        PERF_METRICS['yaml_reads'] += 1
        
        # Choose loader based on validation needs
        loader = FastYAMLLoader if skip_validation else UniqueKeyLoader
        
        if string is not None:
            yaml_data = Box().from_yaml(
                yaml_string=string,
                default_box=True,
                box_dots=True,
                default_box_none_transform=False,
                Loader=loader
            )
        else:
            if "package:" in filename:
                pkg_files = _files.get_traversable_path('package:')
                with pkg_files.joinpath(filename.replace("package:","")).open('r') as fid:
                    yaml_data = Box().from_yaml(
                        yaml_string=fid.read(),
                        default_box=True,
                        box_dots=True,
                        default_box_none_transform=False,
                        Loader=loader
                    )
            else:
                yaml_data = Box().from_yaml(
                    filename=filename,
                    default_box=True,
                    box_dots=True,
                    default_box_none_transform=False,
                    Loader=loader
                )
        
        # Cache the result
        if filename and yaml_data is not None:
            save_to_cache(filename, yaml_data)
        
        return yaml_data
        
    finally:
        PERF_METRICS['total_read_time'] += time.time() - start_time

def include_yaml_parallel(data: Box, source_file: str, max_workers: int = 4) -> None:
    """Process YAML includes in parallel"""
    if not isinstance(data, dict) or '_include' not in data:
        return
    
    # Get include path
    if 'package:' in source_file:
        inc_path = 'package:' + os.path.dirname(source_file.replace('package:',''))
    else:
        inc_path = os.path.dirname(source_file)
    
    # Collect all files to include
    include_tasks = []
    for inc_name in data._include:
        if "~/" in inc_name:
            file_path = os.path.dirname(os.path.expanduser(inc_name))
        else:
            file_path = inc_path + ('/' if '/' in inc_path else '') + os.path.dirname(inc_name)
        
        traversable = _files.get_traversable_path(file_path)
        inc_files = _files.get_globbed_files(traversable, os.path.basename(inc_name))
        
        for file_name in sorted(inc_files):
            include_tasks.append(file_name)
    
    # Process includes in parallel
    included_data = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(read_yaml_fast, file_name): file_name 
            for file_name in include_tasks
        }
        
        for future in concurrent.futures.as_completed(future_to_file):
            file_name = future_to_file[future]
            try:
                yaml_data = future.result()
                if yaml_data is not None:
                    base_name = os.path.splitext(os.path.basename(file_name))[0]
                    included_data[base_name] = yaml_data
            except Exception as e:
                log.error(f'Failed to include {file_name}: {e}')
    
    # Merge included data
    for name, yaml_data in included_data.items():
        if '_top' in yaml_data:
            for k, v in yaml_data._top.items():
                if k not in data:
                    data[k] = v
                elif isinstance(v, Box) and isinstance(data[k], Box):
                    data[k] = data[k] + v
            yaml_data.pop('_top', None)
        
        data[name] = yaml_data
    
    data.pop('_include', None)

def load_optimized(
    fname: str,
    user_defaults: typing.Optional[list] = None,
    system_defaults: typing.Optional[list] = None,
    relative_topo_name: typing.Optional[bool] = False,
    skip_validation: bool = False,
    parallel: bool = True
) -> Box:
    """Optimized topology loading with caching and parallel processing"""
    
    # Show progress for large files
    if not log.QUIET and os.path.exists(fname) and os.path.getsize(fname) > 1024 * 1024:  # > 1MB
        print(f"Loading large topology file: {fname}")
    
    # Generate include hash from defaults for cache key
    defaults_list = build_optimized_defaults_list(user_defaults, system_defaults)
    include_hash = hashlib.md5(json.dumps(defaults_list).encode()).hexdigest()[:8]
    
    # Try to load complete processed topology from cache
    cache_key = f"complete_{include_hash}"
    cached_topology = load_from_cache(fname, cache_key)
    if cached_topology is not None:
        if not log.QUIET:
            print(f"Loaded topology from cache (took {PERF_METRICS['total_read_time']:.2f}s)")
        return cached_topology
    
    # Load main topology file
    if not relative_topo_name and fname.find('package:') != 0:
        fname = str(_files.absolute_path(fname))
    
    topology = read_yaml_fast(fname, skip_validation=skip_validation)
    if topology is None:
        log.fatal(f'Cannot read topology file: {fname}')
    
    topology.input = [fname]
    
    # Process includes in parallel if enabled
    if '_include' in topology and parallel:
        include_yaml_parallel(topology, fname)
    
    # Load defaults in parallel
    if parallel and len(defaults_list) > 2:
        load_defaults_parallel(topology, defaults_list, skip_validation)
    else:
        # Fall back to sequential loading for small lists
        for dfname in defaults_list:
            if dfname.find('package:') != 0:
                dfname = str(_files.absolute_path(dfname, fname))
                if not os.path.isfile(dfname):
                    continue
            
            defaults = read_yaml_fast(dfname, skip_validation=skip_validation)
            if defaults:
                topology.input.append(dfname)
                topology.defaults = defaults + topology.defaults
    
    # Cache the complete processed topology
    save_to_cache(fname, topology, cache_key)
    
    if not log.QUIET and PERF_METRICS['yaml_reads'] > 0:
        print(f"Performance: {PERF_METRICS['cache_hits']} cache hits, "
              f"{PERF_METRICS['cache_misses']} misses, "
              f"{PERF_METRICS['total_read_time']:.2f}s total read time")
    
    return topology

def load_defaults_parallel(topology: Box, defaults_list: list, skip_validation: bool = False) -> None:
    """Load default files in parallel"""
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_to_file = {}
        
        for dfname in defaults_list:
            if dfname.find('package:') != 0:
                dfname = str(_files.absolute_path(dfname, topology.input[0]))
                if not os.path.isfile(dfname):
                    continue
            
            future = executor.submit(read_yaml_fast, dfname, None, skip_validation)
            future_to_file[future] = dfname
        
        # Collect results in order
        defaults_data = []
        for future in concurrent.futures.as_completed(future_to_file):
            dfname = future_to_file[future]
            try:
                defaults = future.result()
                if defaults:
                    defaults_data.append((dfname, defaults))
            except Exception as e:
                log.error(f'Failed to load defaults from {dfname}: {e}')
        
        # Apply defaults in correct order
        for dfname, defaults in sorted(defaults_data, key=lambda x: defaults_list.index(x[0])):
            topology.input.append(dfname)
            topology.defaults = defaults + topology.defaults

def build_optimized_defaults_list(
    user_defaults: typing.Optional[list] = None,
    system_defaults: typing.Optional[list] = None
) -> list:
    """Build optimized defaults list with deduplication"""
    if user_defaults is None:
        user_defaults = USER_DEFAULTS
    if system_defaults is None:
        system_defaults = SYSTEM_DEFAULTS
    
    # Use a set to track seen files and preserve order
    seen = set()
    result = []
    
    for f in user_defaults + system_defaults:
        if f not in seen:
            seen.add(f)
            result.append(f)
    
    return result

def clear_cache() -> None:
    """Clear all cached files"""
    import shutil
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Cleared cache directory: {CACHE_DIR}")

def get_cache_stats() -> dict:
    """Get cache statistics"""
    cache_files = list(CACHE_DIR.glob('*.pkl'))
    total_size = sum(f.stat().st_size for f in cache_files)
    
    return {
        'cache_dir': str(CACHE_DIR),
        'num_files': len(cache_files),
        'total_size_mb': total_size / (1024 * 1024),
        'performance': PERF_METRICS
    }