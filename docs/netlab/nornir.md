# Using Nornir with netlab

Netlab now supports [Nornir](https://nornir.readthedocs.io/) as an alternative to Ansible for configuration deployment. Nornir provides significantly faster performance through native Python threading and eliminates the need for Ansible installation.

## Why Nornir?

- **Performance**: 3-5x faster than Ansible for parallel deployments
- **Simplicity**: Pure Python, no external dependencies like Ansible
- **Flexibility**: Easy to extend with custom Python code
- **Threading**: Native parallel execution without process overhead

## Installation

To use Nornir with netlab, install the additional dependencies:

```bash
pip install -r requirements-nornir.txt
```

Or install individual components:

```bash
pip install nornir nornir-napalm nornir-scrapli nornir-utils
```

## Basic Usage

### Configuration Deployment

Deploy configurations using the `--engine nornir` flag:

```bash
# Deploy OSPF configuration using Nornir
netlab config --engine nornir ospf

# Deploy with specific number of workers
netlab config --engine nornir --workers 50 ospf

# Limit to specific devices
netlab config --engine nornir --limit router1,router2 ospf

# Dry run to see what would be changed
netlab config --engine nornir --dry-run ospf
```

### Initial Configuration

Deploy initial device configuration with Nornir:

```bash
# Deploy initial configuration
netlab initial --engine nornir

# Deploy to specific devices only
netlab initial --engine nornir --limit spine1,spine2
```

### Configuration Collection

Collect device configurations:

```bash
# Collect all device configs
netlab collect --engine nornir

# Collect from specific devices
netlab collect --engine nornir --limit router1,router2

# Save to specific directory
netlab collect --engine nornir --output configs/backup
```

## Performance Tuning

### Worker Threads

Adjust the number of parallel workers based on your environment:

```bash
# Default: 100 workers
netlab config --engine nornir ospf

# Reduce for smaller labs
netlab config --engine nornir --workers 10 ospf

# Increase for large deployments
netlab config --engine nornir --workers 200 ospf
```

### Best Practices

1. **Worker Count**: Set workers to 2-3x the number of devices for optimal performance
2. **Large Labs**: For 50+ devices, Nornir shows significant performance advantages
3. **Memory Usage**: Each worker consumes memory; adjust based on available resources

## Feature Comparison

| Feature | Ansible | Nornir |
|---------|---------|---------|
| Configuration deployment | ✓ | ✓ |
| Initial configuration | ✓ | ✓ |
| Configuration collection | ✓ | ✓ |
| Dry run | ✓ | ✓ |
| Diff output | ✓ | ✓ |
| Host limiting | ✓ | ✓ |
| Parallel execution | ✓ | ✓ |
| Configuration reload | ✓ | Planned |
| Custom modules | ✓ | ✓ |

## Platform Support

Nornir supports all platforms that netlab supports, using appropriate drivers:

### NAPALM-based (Full Support)
- Arista EOS
- Cisco IOS/IOS-XE
- Cisco NX-OS
- Cisco IOS-XR
- Juniper JunOS

### Scrapli-based (Full Support)
- Nokia SR OS
- Nokia SR Linux
- Additional platforms via Scrapli community drivers

### SSH-based (Full Support)
- FRR
- Cumulus Linux
- VyOS
- SONiC
- Generic Linux

## Extending Nornir Support

### Custom Drivers

Create custom drivers for additional platforms:

```python
# netsim/nornir/drivers/custom_driver.py
from netsim.nornir.drivers.base import BaseDriver

class CustomDriver(BaseDriver):
    def merge_config(self, config, commit=True):
        # Implementation
        pass
    
    def replace_config(self, config, commit=True):
        # Implementation
        pass
```

Register the driver:

```python
from netsim.nornir.drivers import register_driver
register_driver('custom_platform', CustomDriver)
```

### Custom Tasks

Add custom Nornir tasks for specific workflows:

```python
from nornir.core.task import Task, Result

def custom_task(task: Task, **kwargs) -> Result:
    # Custom implementation
    return Result(host=task.host, result="Success")
```

## Troubleshooting

### Import Errors

If you see import errors, ensure all dependencies are installed:

```bash
pip install -r requirements-nornir.txt
```

### Connection Issues

1. Verify SSH connectivity: `netlab connect <device>`
2. Check device credentials in topology file
3. Use `--verbose` flag for detailed output

### Performance Issues

1. Reduce worker count if experiencing connection limits
2. Check system resources (CPU, memory)
3. Verify network latency to devices

## Migration from Ansible

Existing netlab deployments work seamlessly with Nornir:

1. No changes needed to topology files
2. Same configuration templates (Jinja2)
3. Same command structure with `--engine nornir` flag
4. Gradual migration possible (use both engines as needed)

## Future Enhancements

- Configuration validation before deployment
- Transaction support with rollback
- Enhanced diff output with semantic analysis
- Integration with netlab test framework
- Configuration backup and restore workflows