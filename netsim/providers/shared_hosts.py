"""
Shared hosts file generation for containerlab

This module implements industry-standard shared configuration file mounting
for containerlab containers, avoiding per-node hosts file generation.

Key optimizations:
1. Generate one hosts file per device type instead of per node
2. Mount hosts files as read-only to prevent modifications
3. Use bind mounts following Docker best practices
4. Eliminate redundant file generation and template processing

Usage:
    Enable by default or set in topology:
    defaults.providers.clab.shared_hosts: true
    
This approach significantly reduces startup time for large topologies
by avoiding N hosts file generations for N nodes.
"""

import os
import pathlib
from typing import Dict, Set
from box import Box
from ..utils import log, templates, files as _files
from ..outputs.ansible import get_host_addresses


def get_device_groups(topology: Box) -> Dict[str, Set[str]]:
    """
    Group nodes by device type to determine which nodes can share hosts files.
    Returns a dictionary mapping device_type -> set of node names
    """
    device_groups: Dict[str, Set[str]] = {}
    
    for name, node in topology.nodes.items():
        device = node.get('device', 'unknown')
        if device not in device_groups:
            device_groups[device] = set()
        device_groups[device].add(name)
    
    return device_groups


def should_use_shared_hosts(topology: Box) -> bool:
    """
    Check if shared hosts files should be used based on configuration.
    Default is True for optimal performance.
    """
    return topology.defaults.providers.clab.get('shared_hosts', True)


def generate_shared_hosts_files(topology: Box, provider_folder: str = "clab_files") -> Dict[str, str]:
    """
    Generate shared hosts files per device type.
    Returns a mapping of device_type -> hosts_file_path
    """
    if not should_use_shared_hosts(topology):
        return {}
    
    device_groups = get_device_groups(topology)
    hosts_files: Dict[str, str] = {}
    
    # Get the complete hosts data
    hosts_data = get_host_addresses(topology)
    
    # Create shared hosts directory
    shared_hosts_dir = f"{provider_folder}/shared_hosts"
    pathlib.Path(shared_hosts_dir).mkdir(parents=True, exist_ok=True)
    
    for device_type in device_groups:
        # Generate hosts file for this device type
        hosts_file_path = f"{shared_hosts_dir}/hosts_{device_type}"
        
        # Prepare template data - use first node of this device type as base
        # This ensures we have all the necessary node context
        first_node_name = next(iter(device_groups[device_type]))
        base_node = topology.nodes[first_node_name]
        
        # Merge with global data like the original implementation
        template_data = base_node + {
            'hostvars': topology.nodes,
            'hosts': hosts_data,
            'addressing': topology.addressing
        }
        
        try:
            # Find the appropriate hosts template
            template_paths = [
                f"templates/provider/clab/{device_type}/hosts.j2",
                "templates/provider/clab/linux/hosts.j2"  # Default fallback
            ]
            
            template_found = False
            for rel_path in template_paths:
                full_path = os.path.join(str(_files.get_moddir()), rel_path)
                if os.path.exists(full_path):
                    # Write the shared hosts file
                    templates.write_template(
                        in_folder=os.path.dirname(full_path),
                        j2=os.path.basename(full_path),
                        data=template_data.to_dict(),
                        out_folder=shared_hosts_dir,
                        filename=f"hosts_{device_type}"
                    )
                    template_found = True
                    break
            
            if not template_found:
                log.error(f"Cannot find hosts template for device type {device_type}", log.MissingValue, 'clab')
                continue
            
            hosts_files[device_type] = hosts_file_path
            log.print_verbose(f"Generated shared hosts file for device type '{device_type}': {hosts_file_path}")
            
        except Exception as ex:
            log.error(
                f"Error generating shared hosts file for device type {device_type}: {ex}",
                category=log.IncorrectValue,
                module='clab'
            )
    
    return hosts_files


def update_node_binds_for_shared_hosts(topology: Box, hosts_files: Dict[str, str]) -> None:
    """
    Update node configurations to use shared hosts files with read-only bind mounts.
    Removes individual hosts file generation and replaces with shared mounts.
    """
    for name, node in topology.nodes.items():
        device = node.get('device', 'unknown')
        
        if device not in hosts_files:
            continue
        
        # Remove individual hosts template if exists
        if 'clab.config_templates' in node:
            templates_dict = {}
            for item in node.clab.config_templates:
                if isinstance(item, str) and ':' in item:
                    src, dst = item.split(':', 1)
                    if dst != '/etc/hosts':
                        templates_dict[src] = dst
                elif isinstance(item, dict):
                    for src, dst in item.items():
                        if dst != '/etc/hosts':
                            templates_dict[src] = dst
            
            # Rebuild config_templates without hosts
            if templates_dict:
                node.clab.config_templates = [f"{src}:{dst}" for src, dst in templates_dict.items()]
            else:
                del node.clab.config_templates
        
        # Add shared hosts file as read-only bind mount
        if 'clab.binds' not in node:
            node.clab.binds = []
        
        # Add the shared hosts file mount with read-only flag
        shared_hosts_mount = f"{hosts_files[device]}:/etc/hosts:ro"
        
        # Check if hosts mount already exists and replace it
        new_binds = []
        hosts_mount_added = False
        
        for bind in node.clab.binds:
            if isinstance(bind, str) and ':/etc/hosts' in bind:
                # Replace existing hosts mount with shared read-only version
                new_binds.append(shared_hosts_mount)
                hosts_mount_added = True
            else:
                new_binds.append(bind)
        
        if not hosts_mount_added:
            new_binds.append(shared_hosts_mount)
        
        node.clab.binds = new_binds
        
        log.print_verbose(f"Node '{name}' configured to use shared hosts file for device type '{device}'")