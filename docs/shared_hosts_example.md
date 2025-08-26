# Shared Hosts File Optimization for Containerlab

## Overview

This optimization implements industry-standard shared configuration file mounting for containerlab containers. Instead of generating individual `/etc/hosts` files for each container, we generate one shared hosts file per device type and mount it read-only into all containers of that type.

## Benefits

1. **Performance**: Eliminates redundant file generation (from N files to M device types)
2. **Consistency**: All containers of the same type share identical host mappings
3. **Security**: Read-only mounts prevent containers from modifying host entries
4. **Simplicity**: Follows Docker best practices for shared configuration

## Configuration

Enable shared hosts files (default: true):
```yaml
defaults:
  providers:
    clab:
      shared_hosts: true
```

## How It Works

1. **Device Grouping**: Nodes are grouped by device type (e.g., all 'linux' nodes together)
2. **Shared Generation**: One hosts file is generated per device type in `clab_files/shared_hosts/`
3. **Read-Only Mounting**: Each container gets the shared file mounted as `/etc/hosts:ro`

## Example

For a topology with 10 Linux hosts and 5 FRR routers:
- **Before**: 15 individual hosts files generated
- **After**: 2 shared hosts files (one for Linux, one for FRR)

## Implementation Details

The shared hosts file is mounted using Docker's bind mount syntax:
```
/path/to/shared/hosts_linux:/etc/hosts:ro
```

The `:ro` flag ensures the mount is read-only, following security best practices.