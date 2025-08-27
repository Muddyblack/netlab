# Nornir Demo

This example demonstrates using Nornir as an alternative to Ansible for configuration deployment in netlab.

## Prerequisites

1. Install netlab and dependencies
2. Install Nornir dependencies:
   ```bash
   pip install -r ../../requirements-nornir.txt
   ```

## Running the Demo

1. Create and start the lab:
   ```bash
   netlab up
   ```

2. Deploy initial configuration using Nornir:
   ```bash
   netlab initial --engine nornir
   ```

3. Create a custom configuration template:
   ```bash
   mkdir -p templates
   cat > templates/custom.frr.j2 << 'EOF'
   router bgp {{ bgp.as }}
    neighbor {{ bgp.peer }} remote-as {{ bgp.peer_as }}
    network {{ bgp.network }}/{{ bgp.prefix }}
   EOF
   ```

4. Deploy custom configuration:
   ```bash
   netlab config --engine nornir templates/custom
   ```

## Performance Comparison

Compare Ansible vs Nornir performance:

```bash
# Time Ansible deployment
time netlab initial --engine ansible

# Time Nornir deployment  
time netlab initial --engine nornir
```

For this small topology, the difference might be minimal, but for larger topologies (20+ devices), Nornir typically shows 3-5x performance improvement.

## Features to Try

1. **Dry Run**:
   ```bash
   netlab config --engine nornir --dry-run ospf
   ```

2. **Limited Deployment**:
   ```bash
   netlab config --engine nornir --limit r1,r2 ospf
   ```

3. **Configuration Collection**:
   ```bash
   netlab collect --engine nornir --output configs/
   ```

4. **Parallel Workers**:
   ```bash
   # Reduce workers for this small topology
   netlab initial --engine nornir --workers 3
   ```

## Cleanup

```bash
netlab down
```