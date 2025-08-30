# Faster Extra File Mapping with Generic Shared File Mechanism

This PR implements a clean, generic shared file mechanism that dramatically improves performance for large topologies (600+ nodes) by reducing file generation time from ~10 minutes to ~1-2 minutes.

## Summary of Changes

### 1. Generic `:shared` Marker Support
- Added support for `:shared` marker in file mappings (e.g., `hosts: /etc/hosts:shared`)
- Files marked with `:shared` are:
  - Generated once and stored in `{provider}_files/shared/` directory
  - Automatically mounted as read-only (`:ro`) in containers
  - Cached to avoid regeneration for subsequent nodes

### 2. Provider Implementation (`netsim/providers/__init__.py`)
- Added `_shared_files_cache` to track generated shared files
- Modified `create_extra_files()` to detect and handle `:shared` markers
- Pre-compute host addresses once instead of per-node
- Simplified logic without complex multiprocessing or unnecessary caching

### 3. Device Configuration Updates
- Updated Linux, FRR, and Cumulus devices to use shared hosts files
- Changed `hosts: /etc/hosts` to `hosts: /etc/hosts:shared`

## Performance Impact

For a topology with 610 devices:
- **Before**: ~10 minutes
- **After**: ~1-2 minutes

The improvement comes from:
1. Generating the hosts file once per device type instead of per node
2. Pre-computing host addresses once for the entire topology
3. Eliminating redundant `to_dict()` calls

## Design Principles

Following @ipspace's guidance:
- Simple, maintainable code that we'll understand a year from now
- Generic solution that can be applied to any file, not just hosts
- No breaking changes to existing functionality
- Clean implementation without over-engineering

## How It Works

1. When a template includes `:shared` in its mapping, the provider generates the file once in a shared location
2. The `:shared` marker is replaced with `:ro` for read-only container mounting
3. Subsequent nodes reuse the cached file path instead of regenerating the file
4. The existing Jinja2 template mechanism is used unchanged

## Testing

The implementation maintains backward compatibility - files without `:shared` continue to work as before. The shared file mechanism is opt-in and can be applied selectively based on requirements.

Fixes the performance issues discussed in #2621 and #2628.