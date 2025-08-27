# Nornir Integration Design for netlab

## Overview

This document outlines the design for integrating Nornir as an alternative configuration deployment mechanism for netlab. The goal is to provide a faster alternative to Ansible while maintaining compatibility with existing inventory, templates, and workflows.

## Design Principles

1. **Compatibility**: Reuse existing Ansible inventory, Jinja2 templates, and configuration structure
2. **Performance**: Leverage Nornir's threading capabilities for faster deployment
3. **Flexibility**: Allow users to choose between Ansible and Nornir based on their needs
4. **Simplicity**: Minimal changes to existing workflows and commands

## Architecture

### Components

1. **Inventory Adapter** (`netsim/nornir/inventory.py`)
   - Convert Ansible inventory to Nornir format
   - Support for host variables, groups, and connection parameters
   - Handle provider-specific connection methods

2. **Configuration Tasks** (`netsim/nornir/tasks.py`)
   - Template rendering using existing Jinja2 templates
   - Device-specific deployment tasks
   - Error handling and reporting

3. **CLI Integration** (`netsim/cli/nornir_config.py`)
   - New `--engine nornir` flag for config commands
   - Backward compatibility with existing commands
   - Progress reporting and logging

4. **Device Drivers** (`netsim/nornir/drivers/`)
   - Support for common network operating systems
   - Leverage Nornir plugins (NAPALM, Scrapli, Netmiko)
   - Custom drivers for specific platforms

## Implementation Plan

### Phase 1: Core Infrastructure
- Create Nornir module structure
- Implement inventory adapter
- Basic template rendering

### Phase 2: Device Support
- Implement drivers for major platforms (IOS, EOS, JunOS, FRR)
- Connection handling and authentication
- Error recovery mechanisms

### Phase 3: CLI Integration
- Add engine selection to existing commands
- Progress reporting and logging
- Performance benchmarking

### Phase 4: Advanced Features
- Parallel execution control
- Dry-run support
- Configuration validation

## Usage Examples

### Basic Configuration Deployment
```bash
# Using Ansible (default)
netlab config ospf

# Using Nornir
netlab config --engine nornir ospf

# With specific hosts
netlab config --engine nornir --limit router1,router2 ospf
```

### Initial Configuration
```bash
# Deploy initial configuration with Nornir
netlab initial --engine nornir

# Deploy with custom thread count
netlab initial --engine nornir --threads 10
```

## Performance Considerations

- Thread pool size configuration
- Connection caching
- Template rendering optimization
- Progress reporting without sacrificing performance

## Compatibility Matrix

| Feature | Ansible | Nornir |
|---------|---------|---------|
| Inventory | Native | Adapted |
| Templates | Jinja2 | Jinja2 |
| Connections | Network modules | NAPALM/Scrapli |
| Parallel execution | Strategy plugins | Native threading |
| Dry run | Check mode | Custom implementation |

## Dependencies

New Python packages required:
- nornir >= 3.3.0
- nornir-napalm >= 0.4.0
- nornir-scrapli >= 2023.1.30
- nornir-netmiko >= 1.0.0
- nornir-utils >= 0.2.0

## Migration Strategy

1. Both engines coexist during transition
2. Default remains Ansible
3. Users opt-in to Nornir
4. Gradual feature parity
5. Future consideration for default engine change

## Testing Strategy

- Unit tests for inventory conversion
- Integration tests with mock devices
- Performance benchmarks
- Compatibility tests with existing templates