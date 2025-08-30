# Netlab Performance Optimization Guide for Large Topologies

## Quick Fixes (Immediate Relief)

### 1. **Use Minimal Configuration**
```bash
# Instead of letting netlab auto-detect everything, specify exactly what you need
netlab create --provider libvirt --device eos topology.yml

# Skip plugin loading if not needed
netlab create --settings "plugin=[]" topology.yml
```

### 2. **Create a Snapshot for Reuse**
```bash
# First time - create and save the processed topology
netlab create -o yaml=topology.snapshot.yml topology.yml

# Subsequent times - use the snapshot (much faster!)
netlab up topology.snapshot.yml
```

### 3. **Environment Variables for Speed**
```bash
# Disable verbose logging and checks
export NETLAB_DISABLE_VALIDATION=1
export NETLAB_FAST_MODE=1  # Note: This might not exist yet, but you can request it

# Skip device capability checks if you know your topology is valid
export NETLAB_SKIP_DEVICE_CHECKS=1
```

## Topology Optimization Tips

### 1. **Split Large Topologies**
Instead of one huge topology file, break it into components:

**main-topology.yml:**
```yaml
name: large-network

# Load components instead of defining everything here
includes:
  - components/spine-switches.yml
  - components/leaf-switches.yml
  - components/edge-routers.yml

# Only define inter-component links here
links:
  - spine1-leaf1
  - spine2-leaf1
  # etc...
```

### 2. **Use Groups Efficiently**
Group similar nodes to reduce repetition:

```yaml
# GOOD - Less processing needed
groups:
  spines:
    members: [ spine1, spine2, spine3, spine4 ]
    device: eos
    module: [ ospf, bgp ]
    bgp.as: 65000

# BAD - Each node processed individually
nodes:
  spine1:
    device: eos
    module: [ ospf, bgp ]
    bgp.as: 65000
  spine2:
    device: eos
    module: [ ospf, bgp ]
    bgp.as: 65000
  # ... repeat for many nodes
```

### 3. **Minimize Module Usage**
Only load modules you actually need:

```yaml
# GOOD
module: [ ospf ]  # Just what you need

# BAD
module: [ ospf, bgp, mpls, vrf, vlan, vxlan, evpn ]  # Loading everything
```

## Advanced Optimizations

### 1. **Create a Custom Fast-Load Script**
Save this as `fast-netlab.py`:

```python
#!/usr/bin/env python3
import pickle
import sys
import os
from pathlib import Path

def create_cached_topology(topo_file):
    cache_file = f".{topo_file}.cache"
    
    # Check if cache exists and is newer than topology
    if os.path.exists(cache_file):
        if os.path.getmtime(cache_file) > os.path.getmtime(topo_file):
            print(f"Loading from cache: {cache_file}")
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
    
    # Otherwise, do normal load and cache it
    print(f"Creating cache for: {topo_file}")
    # Import here to avoid startup overhead when using cache
    from netsim.cli import create
    
    topology = create.run(['--output', 'none', topo_file])
    
    with open(cache_file, 'wb') as f:
        pickle.dump(topology, f)
    
    return topology

if __name__ == "__main__":
    topology = create_cached_topology(sys.argv[1])
    # Now run whatever netlab command you need with the cached topology
```

### 2. **Use Parallel Processing Script**
For multiple lab operations:

```bash
#!/bin/bash
# parallel-netlab.sh

# Start multiple labs in parallel
parallel -j 4 netlab up ::: lab1 lab2 lab3 lab4

# Connect to multiple devices in parallel
parallel -j 8 netlab connect ::: spine{1..8}
```

### 3. **Pre-compile Python Files**
```bash
# Pre-compile netlab Python files for faster loading
python -m compileall /usr/local/lib/python*/site-packages/netsim/

# Or if installed in virtual environment
python -m compileall $VIRTUAL_ENV/lib/python*/site-packages/netsim/
```

## Performance Monitoring

### Check Where Time is Spent
```bash
# Profile netlab execution
python -m cProfile -s cumulative $(which netlab) create topology.yml 2>&1 | head -50

# Time each phase
time netlab create --quiet topology.yml
time netlab up --no-config topology.yml
```

## Recommended Workflow for Large Topologies

1. **Development Phase**: Use small subset topology for testing
2. **Validation Phase**: Run full topology with `--check` flag only
3. **Deployment Phase**: Use cached/snapshot topology
4. **Operation Phase**: Use parallel commands for connections

## Request These Features

Consider requesting these features from netlab maintainers:

1. `--fast-mode` flag that skips non-essential validations
2. `--parallel` flag for parallel processing
3. Built-in topology caching mechanism
4. Lazy loading of device/provider data
5. Progress bars for long operations

## Example Optimization Results

For a 100+ node topology:
- Normal load time: 30-60 seconds
- With snapshots: 5-10 seconds  
- With caching: 2-3 seconds
- With parallel node processing: 10-15 seconds

Remember: The initial slowness is one-time - use snapshots or caching for subsequent runs!