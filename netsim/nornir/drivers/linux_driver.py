#
# Linux driver for Nornir configuration deployment
#
# Handles FRR, Cumulus, VyOS, SONiC and other Linux-based network OSes
#

import typing
import tempfile
from pathlib import Path
from nornir_utils.plugins.tasks import remote_command
from nornir.core.exceptions import NornirExecutionError
from .base import BaseDriver


class LinuxDriver(BaseDriver):
    """
    Driver for Linux-based network operating systems
    """
    
    def __init__(self, task):
        super().__init__(task)
        self.platform_config = {
            'frr': {
                'config_file': '/etc/frr/frr.conf',
                'reload_cmd': 'sudo systemctl reload frr',
                'validate_cmd': 'sudo vtysh -c "show running-config" > /dev/null',
                'show_config_cmd': 'sudo vtysh -c "show running-config"',
                'merge_cmd': 'sudo vtysh -f {config_file}',
                'replace_cmd': 'sudo cp {config_file} /etc/frr/frr.conf && sudo systemctl reload frr'
            },
            'cumulus': {
                'config_file': '/etc/frr/frr.conf',
                'reload_cmd': 'sudo systemctl reload frr',
                'validate_cmd': 'sudo vtysh -c "show running-config" > /dev/null',
                'show_config_cmd': 'sudo vtysh -c "show running-config"',
                'merge_cmd': 'sudo vtysh -f {config_file}',
                'replace_cmd': 'sudo cp {config_file} /etc/frr/frr.conf && sudo systemctl reload frr'
            },
            'vyos': {
                'config_file': '/config/config.boot',
                'reload_cmd': 'sudo systemctl restart vyos-configd',
                'validate_cmd': 'vyos-configd-client --show | head -n 1',
                'show_config_cmd': 'cat /config/config.boot',
                'merge_cmd': 'echo "{config}" | vyos-configd-client --load',
                'replace_cmd': 'sudo cp {config_file} /config/config.boot && sudo systemctl restart vyos-configd'
            },
            'sonic': {
                'config_file': '/etc/sonic/config_db.json',
                'reload_cmd': 'sudo config reload -y',
                'validate_cmd': 'sudo config validate',
                'show_config_cmd': 'sudo config export',
                'merge_cmd': 'echo "{config}" | sudo config apply -',
                'replace_cmd': 'sudo config replace {config_file} -y'
            },
            'linux': {
                # Generic Linux - mainly for configuration of network interfaces
                'config_file': '/tmp/netlab_config.sh',
                'reload_cmd': 'true',  # No reload needed
                'validate_cmd': 'true',  # Always valid
                'show_config_cmd': 'ip addr show',
                'merge_cmd': 'bash {config_file}',
                'replace_cmd': 'bash {config_file}'
            }
        }
    
    def connect(self) -> None:
        """
        SSH connection is handled by Nornir
        """
        pass
    
    def close(self) -> None:
        """
        Connection cleanup is handled by Nornir
        """
        pass
    
    def _get_platform_config(self) -> dict:
        """
        Get platform-specific configuration commands
        """
        platform = self.host.data.get('netlab_device_type', self.host.platform)
        return self.platform_config.get(platform, self.platform_config['linux'])
    
    def _run_command(self, command: str) -> str:
        """
        Run a command on the remote host
        """
        result = self.task.run(task=remote_command, command=command)
        
        if result.failed:
            raise Exception(f"Command failed: {result.result}")
        
        return result.result
    
    def _upload_config(self, config: str) -> str:
        """
        Upload configuration to a temporary file on the remote host
        """
        # Create a temporary file locally
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.conf') as f:
            f.write(config)
            local_file = f.name
        
        # Generate remote filename
        remote_file = f"/tmp/netlab_config_{self.host.name}.conf"
        
        # Upload file using SCP/SFTP
        # This is a simplified version - in production, we'd use a proper file transfer method
        try:
            # Use base64 encoding to transfer file content
            import base64
            encoded = base64.b64encode(config.encode()).decode()
            self._run_command(f"echo '{encoded}' | base64 -d > {remote_file}")
            self._run_command(f"chmod 644 {remote_file}")
        finally:
            # Clean up local file
            Path(local_file).unlink(missing_ok=True)
        
        return remote_file
    
    def merge_config(self, config: str, commit: bool = True) -> dict:
        """
        Merge configuration on Linux-based system
        """
        platform_config = self._get_platform_config()
        
        if not commit:
            # Just validate the configuration
            return {'changed': False, 'result': 'Dry run - no changes made'}
        
        # Upload configuration
        config_file = self._upload_config(config)
        
        try:
            # Apply configuration
            merge_cmd = platform_config['merge_cmd'].format(
                config_file=config_file,
                config=config
            )
            result = self._run_command(merge_cmd)
            
            # Validate if command exists
            if platform_config['validate_cmd'] != 'true':
                self._run_command(platform_config['validate_cmd'])
            
            return {
                'changed': True,
                'result': result
            }
            
        finally:
            # Clean up remote file
            self._run_command(f"rm -f {config_file}")
    
    def replace_config(self, config: str, commit: bool = True) -> dict:
        """
        Replace entire configuration on Linux-based system
        """
        platform_config = self._get_platform_config()
        
        if not commit:
            return {'changed': False, 'result': 'Dry run - no changes made'}
        
        # Backup current configuration
        backup_file = f"/tmp/netlab_backup_{self.host.name}.conf"
        if platform_config['config_file'] != '/tmp/netlab_config.sh':
            self._run_command(f"sudo cp {platform_config['config_file']} {backup_file}")
        
        # Upload new configuration
        config_file = self._upload_config(config)
        
        try:
            # Replace configuration
            replace_cmd = platform_config['replace_cmd'].format(
                config_file=config_file,
                config=config
            )
            result = self._run_command(replace_cmd)
            
            # Validate
            if platform_config['validate_cmd'] != 'true':
                self._run_command(platform_config['validate_cmd'])
            
            return {
                'changed': True,
                'result': result
            }
            
        except Exception as e:
            # Restore backup on failure
            if platform_config['config_file'] != '/tmp/netlab_config.sh':
                self._run_command(f"sudo cp {backup_file} {platform_config['config_file']}")
                self._run_command(platform_config['reload_cmd'])
            raise e
            
        finally:
            # Clean up files
            self._run_command(f"rm -f {config_file} {backup_file}")
    
    def get_config(self, command: typing.Optional[str] = None) -> str:
        """
        Get running configuration from Linux-based system
        """
        platform_config = self._get_platform_config()
        cmd = command or platform_config['show_config_cmd']
        return self._run_command(cmd)
    
    def send_command(self, command: str) -> str:
        """
        Send a command to the Linux system
        """
        return self._run_command(command)