#!/usr/bin/env python3
#
# Test Nornir integration for netlab
#

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from box import Box

# Import modules to test
from netsim.nornir.inventory import AnsibleInventoryAdapter
from netsim.nornir.tasks import render_template, find_custom_template
from netsim.nornir.drivers import get_driver, BaseDriver


class TestInventoryAdapter:
    """Test Ansible to Nornir inventory conversion"""
    
    @pytest.fixture
    def mock_ansible_inventory(self):
        """Mock ansible-inventory output"""
        return {
            "_meta": {
                "hostvars": {
                    "router1": {
                        "ansible_host": "192.168.1.1",
                        "ansible_user": "admin",
                        "ansible_password": "secret",
                        "netlab_device_type": "ios",
                        "ansible_network_os": "ios"
                    },
                    "router2": {
                        "ansible_host": "192.168.1.2",
                        "ansible_user": "admin",
                        "ansible_ssh_private_key_file": "/path/to/key",
                        "netlab_device_type": "eos",
                        "ansible_network_os": "eos"
                    }
                }
            },
            "all": {
                "hosts": ["router1", "router2"]
            },
            "routers": {
                "hosts": ["router1", "router2"]
            }
        }
    
    @patch('subprocess.run')
    def test_inventory_conversion(self, mock_run, mock_ansible_inventory):
        """Test basic inventory conversion"""
        # Mock ansible-inventory command
        mock_run.return_value.stdout = json.dumps(mock_ansible_inventory)
        mock_run.return_value.returncode = 0
        
        adapter = AnsibleInventoryAdapter()
        
        # Mock host data retrieval
        def mock_host_data(cmd_args, **kwargs):
            result = Mock()
            if '--host' in cmd_args and 'router1' in cmd_args:
                result.stdout = json.dumps(mock_ansible_inventory['_meta']['hostvars']['router1'])
            elif '--host' in cmd_args and 'router2' in cmd_args:
                result.stdout = json.dumps(mock_ansible_inventory['_meta']['hostvars']['router2'])
            else:
                result.stdout = json.dumps(mock_ansible_inventory)
            result.returncode = 0
            return result
        
        mock_run.side_effect = mock_host_data
        
        # Convert to Nornir
        inventory = adapter.to_nornir()
        
        # Verify hosts
        assert len(inventory.hosts) == 2
        assert 'router1' in inventory.hosts
        assert 'router2' in inventory.hosts
        
        # Verify host attributes
        r1 = inventory.hosts['router1']
        assert r1.hostname == '192.168.1.1'
        assert r1.username == 'admin'
        assert r1.password == 'secret'
        assert r1.platform == 'cisco_ios'
        
        r2 = inventory.hosts['router2']
        assert r2.hostname == '192.168.1.2'
        assert r2.platform == 'arista_eos'
    
    @patch('subprocess.run')
    def test_inventory_with_limit(self, mock_run, mock_ansible_inventory):
        """Test inventory conversion with host limit"""
        mock_run.return_value.stdout = json.dumps(mock_ansible_inventory)
        mock_run.return_value.returncode = 0
        
        adapter = AnsibleInventoryAdapter()
        
        # Mock limited host data
        def mock_host_data(cmd_args, **kwargs):
            result = Mock()
            if '--host' in cmd_args and 'router1' in cmd_args:
                result.stdout = json.dumps(mock_ansible_inventory['_meta']['hostvars']['router1'])
            else:
                result.stdout = json.dumps(mock_ansible_inventory)
            result.returncode = 0
            return result
        
        mock_run.side_effect = mock_host_data
        
        # Convert with limit
        inventory = adapter.to_nornir(limit=['router1'])
        
        # Verify only router1 is included
        assert len(inventory.hosts) == 1
        assert 'router1' in inventory.hosts
        assert 'router2' not in inventory.hosts


class TestNornirTasks:
    """Test Nornir task functions"""
    
    def test_render_template(self):
        """Test Jinja2 template rendering"""
        # Create a mock task
        task = Mock()
        task.host = Mock()
        task.host.name = 'router1'
        task.host.hostname = '192.168.1.1'
        task.host.data = Box({
            'interfaces': [
                {'name': 'eth0', 'ip': '10.0.0.1/24'},
                {'name': 'eth1', 'ip': '10.0.1.1/24'}
            ],
            'ospf': {
                'area': '0.0.0.0',
                'router_id': '1.1.1.1'
            }
        })
        
        # Create a temporary template
        with tempfile.NamedTemporaryFile(mode='w', suffix='.j2', delete=False) as f:
            f.write("""
router ospf
  router-id {{ ospf.router_id }}
  network {{ ospf.area }} area 0
{% for intf in interfaces %}
  interface {{ intf.name }}
    ip address {{ intf.ip }}
{% endfor %}
""")
            template_path = f.name
        
        try:
            # Render template
            result = render_template(task, template_path)
            
            # Verify result
            assert not result.failed
            assert 'router-id 1.1.1.1' in result.result
            assert 'interface eth0' in result.result
            assert 'ip address 10.0.0.1/24' in result.result
        finally:
            Path(template_path).unlink()
    
    def test_find_custom_template(self):
        """Test custom template finding logic"""
        # Create mock task
        task = Mock()
        task.host = Mock()
        task.host.name = 'router1'
        task.host.platform = 'cisco_ios'
        task.host.data = Box({
            'netlab_device_type': 'ios',
            'netlab_provider': 'clab'
        })
        
        # Create temporary directory structure
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test templates
            templates = [
                'ospf.j2',
                'ospf.ios.j2',
                'ospf.router1.j2',
                'ospf.ios.clab.j2'
            ]
            
            for template in templates:
                Path(tmpdir, template).touch()
            
            # Test finding templates
            result = find_custom_template(task, 'ospf', [tmpdir])
            assert result == str(Path(tmpdir, 'ospf.j2'))
            
            # Test with specific template name
            result = find_custom_template(task, 'ospf.ios.j2', [tmpdir])
            assert result == str(Path(tmpdir, 'ospf.ios.j2'))
            
            # Test non-existent template
            result = find_custom_template(task, 'bgp', [tmpdir])
            assert result is None


class TestDrivers:
    """Test driver infrastructure"""
    
    def test_get_driver(self):
        """Test driver retrieval"""
        from netsim.nornir.drivers import NapalmDriver, ScrapliDriver, LinuxDriver
        
        # Test known platforms
        assert get_driver('cisco_ios') == NapalmDriver
        assert get_driver('arista_eos') == NapalmDriver
        assert get_driver('nokia_sros') == ScrapliDriver
        assert get_driver('linux') == LinuxDriver
        assert get_driver('frr') == LinuxDriver
        
        # Test unknown platform
        assert get_driver('unknown_platform') is None
    
    def test_base_driver_interface(self):
        """Test that drivers implement required interface"""
        from netsim.nornir.drivers import BaseDriver
        
        # Verify abstract methods
        task = Mock()
        driver = BaseDriver.__new__(BaseDriver)
        driver.__init__(task)
        
        # These should raise NotImplementedError
        with pytest.raises(NotImplementedError):
            driver.connect()
        
        with pytest.raises(NotImplementedError):
            driver.merge_config('config')


# Run tests if executed directly
if __name__ == '__main__':
    pytest.main([__file__, '-v'])