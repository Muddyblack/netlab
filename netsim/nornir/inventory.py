#
# Ansible to Nornir inventory adapter
#
# This module converts netlab's Ansible inventory to Nornir format
# while preserving all host variables and connection parameters
#

import json
import os
import subprocess
import typing
from pathlib import Path

from box import Box
from nornir import InitNornir
from nornir.core.inventory import Host, Groups, Hosts, Inventory

from ..utils import log


class AnsibleInventoryAdapter:
    """
    Adapter to convert Ansible inventory to Nornir inventory format
    """
    
    def __init__(self, ansible_inventory_path: str = "netlab.yml"):
        self.inventory_path = ansible_inventory_path
        self._ansible_data = None
        self._provider_mapping = {
            'ios': 'cisco_ios',
            'eos': 'arista_eos',
            'nxos': 'cisco_nxos',
            'junos': 'juniper_junos',
            'iosxr': 'cisco_xr',
            'frr': 'linux',
            'cumulus': 'linux',
            'linux': 'linux',
            'vyos': 'vyos',
            'sros': 'nokia_sros',
            'srlinux': 'nokia_srlinux',
            'sonic': 'linux',
        }
        
    def _get_ansible_inventory(self) -> dict:
        """
        Execute ansible-inventory to get the complete inventory data
        """
        if self._ansible_data:
            return self._ansible_data
            
        try:
            result = subprocess.run(
                ['ansible-inventory', '-i', self.inventory_path, '--list'],
                capture_output=True,
                check=True,
                text=True
            )
            self._ansible_data = json.loads(result.stdout)
            return self._ansible_data
        except subprocess.CalledProcessError as e:
            log.fatal(f'Failed to get Ansible inventory: {e.stderr}', 'nornir')
        except json.JSONDecodeError as e:
            log.fatal(f'Failed to parse Ansible inventory JSON: {e}', 'nornir')
    
    def _get_host_data(self, hostname: str) -> dict:
        """
        Get host-specific data from ansible-inventory
        """
        try:
            result = subprocess.run(
                ['ansible-inventory', '-i', self.inventory_path, '--host', hostname],
                capture_output=True,
                check=True,
                text=True
            )
            return json.loads(result.stdout)
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            log.error(f'Failed to get host data for {hostname}: {e}', 'nornir')
            return {}
    
    def _create_nornir_host(self, hostname: str, host_data: dict) -> Host:
        """
        Convert Ansible host data to Nornir Host object
        """
        # Extract connection parameters
        ansible_host = host_data.get('ansible_host', hostname)
        ansible_port = host_data.get('ansible_port', 22)
        ansible_user = host_data.get('ansible_user', 'admin')
        ansible_password = host_data.get('ansible_password')
        ansible_ssh_private_key = host_data.get('ansible_ssh_private_key_file')
        
        # Get device type
        netlab_device_type = host_data.get('netlab_device_type', '')
        ansible_network_os = host_data.get('ansible_network_os', netlab_device_type)
        platform = self._provider_mapping.get(ansible_network_os, 'linux')
        
        # Create connection options based on device type
        connection_options = {}
        
        # Common SSH parameters
        ssh_params = {
            'port': ansible_port,
            'username': ansible_user,
            'password': ansible_password,
            'ssh_config_file': host_data.get('ansible_ssh_common_args', '').replace('-F ', ''),
            'ssh_key_file': ansible_ssh_private_key,
            'extras': {
                'ssh_strict_host_key_checking': False,
                'allow_agent': False
            }
        }
        
        # Add connection options for different plugins
        if platform != 'linux':
            # Network devices
            connection_options['napalm'] = {
                'platform': platform,
                'hostname': ansible_host,
                'username': ansible_user,
                'password': ansible_password,
                'optional_args': {}
            }
            
            connection_options['scrapli'] = {
                'platform': platform,
                'host': ansible_host,
                'auth_username': ansible_user,
                'auth_password': ansible_password,
                'auth_strict_key': False,
                'ssh_config_file': ssh_params['ssh_config_file'],
                'auth_private_key': ansible_ssh_private_key
            }
            
            connection_options['netmiko'] = {
                'device_type': platform,
                'host': ansible_host,
                'username': ansible_user,
                'password': ansible_password,
                'port': ansible_port,
                'ssh_config_file': ssh_params['ssh_config_file'],
                'use_keys': bool(ansible_ssh_private_key),
                'key_file': ansible_ssh_private_key
            }
        else:
            # Linux hosts
            connection_options['paramiko'] = ssh_params
            connection_options['ssh'] = ssh_params
        
        # Create Nornir host
        return Host(
            name=hostname,
            hostname=ansible_host,
            port=ansible_port,
            username=ansible_user,
            password=ansible_password,
            platform=platform,
            data=Box(host_data),  # Store all Ansible variables
            connection_options=connection_options
        )
    
    def to_nornir(self, limit: typing.Optional[typing.List[str]] = None) -> Inventory:
        """
        Convert Ansible inventory to Nornir inventory
        
        Args:
            limit: Optional list of hosts to include (similar to ansible --limit)
            
        Returns:
            Nornir Inventory object
        """
        ansible_inv = self._get_ansible_inventory()
        hosts = Hosts()
        groups = Groups()
        
        # Get all hosts
        all_hosts = set()
        for group_name, group_data in ansible_inv.items():
            if group_name == '_meta':
                continue
            if 'hosts' in group_data:
                all_hosts.update(group_data['hosts'])
        
        # Filter hosts if limit is specified
        if limit:
            all_hosts = all_hosts.intersection(set(limit))
        
        # Create Nornir hosts
        for hostname in all_hosts:
            host_data = self._get_host_data(hostname)
            if host_data:
                hosts[hostname] = self._create_nornir_host(hostname, host_data)
        
        # Create groups
        for group_name, group_data in ansible_inv.items():
            if group_name == '_meta':
                continue
                
            group_hosts = []
            if 'hosts' in group_data:
                # Only include hosts that are in our filtered set
                group_hosts = [h for h in group_data['hosts'] if h in hosts]
            
            if group_hosts:
                groups[group_name] = {
                    'hosts': group_hosts,
                    'data': group_data.get('vars', {})
                }
        
        return Inventory(hosts=hosts, groups=groups)
    
    def create_nornir_object(self, limit: typing.Optional[typing.List[str]] = None,
                            num_workers: int = 100) -> InitNornir:
        """
        Create a Nornir object with the converted inventory
        
        Args:
            limit: Optional list of hosts to include
            num_workers: Number of parallel workers (default: 100)
            
        Returns:
            Nornir object ready for use
        """
        inventory = self.to_nornir(limit=limit)
        
        return InitNornir(
            inventory=inventory,
            runner={
                'plugin': 'threaded',
                'options': {
                    'num_workers': num_workers
                }
            },
            logging={
                'enabled': False  # We'll use netlab's logging
            }
        )