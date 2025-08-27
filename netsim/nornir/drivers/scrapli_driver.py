#
# Scrapli driver for Nornir configuration deployment
#

import typing

# Lazy imports to avoid dependency issues
def _get_scrapli_tasks():
    try:
        from nornir_scrapli.tasks import send_config, send_command
        return send_config, send_command
    except ImportError:
        raise ImportError("nornir-scrapli is required for Scrapli driver. Install with: pip install nornir-scrapli")

from .base import BaseDriver


class ScrapliDriver(BaseDriver):
    """
    Driver using Scrapli for configuration deployment
    """
    
    def __init__(self, task):
        super().__init__(task)
        self._config_before = None
        self._config_after = None
    
    def connect(self) -> None:
        """
        Scrapli handles connections internally
        """
        pass
    
    def close(self) -> None:
        """
        Scrapli handles connection cleanup internally
        """
        pass
    
    def _get_running_config(self) -> str:
        """
        Get current running configuration
        """
        # Platform-specific commands
        platform_commands = {
            'cisco_iosxe': 'show running-config',
            'cisco_ios': 'show running-config',
            'cisco_nxos': 'show running-config',
            'cisco_iosxr': 'show running-config',
            'arista_eos': 'show running-config',
            'juniper_junos': 'show configuration',
            'nokia_sros': 'admin display-config',
            'nokia_srlinux': 'info'
        }
        
        command = platform_commands.get(self.host.platform, 'show running-config')
        _, send_command = _get_scrapli_tasks()
        result = self.task.run(task=send_command, command=command)
        
        if not result.failed:
            return result.result
        else:
            raise Exception(f"Failed to get running config: {result.result}")
    
    def merge_config(self, config: str, commit: bool = True) -> dict:
        """
        Merge configuration using Scrapli
        """
        # Get config before change
        if commit:
            self._config_before = self._get_running_config()
        
        # Send configuration
        config_lines = config.strip().split('\n')
        send_config, _ = _get_scrapli_tasks()
        result = self.task.run(
            task=send_config,
            config=config_lines,
            commit=commit
        )
        
        if result.failed:
            raise Exception(f"Configuration merge failed: {result.result}")
        
        # Get config after change
        if commit:
            self._config_after = self._get_running_config()
        
        return {
            'changed': True,  # Scrapli doesn't provide easy diff detection
            'result': result.result
        }
    
    def replace_config(self, config: str, commit: bool = True) -> dict:
        """
        Replace configuration using Scrapli
        
        Note: Full config replace is platform-specific and may not be
        supported on all platforms via Scrapli
        """
        # For most platforms, we'll need to handle this specially
        # This is a simplified implementation
        return self.merge_config(config, commit)
    
    def get_diff(self) -> typing.Optional[str]:
        """
        Generate a simple diff between before/after configs
        """
        if self._config_before and self._config_after:
            # Simple line-based diff
            before_lines = set(self._config_before.strip().split('\n'))
            after_lines = set(self._config_after.strip().split('\n'))
            
            added = after_lines - before_lines
            removed = before_lines - after_lines
            
            diff = []
            if removed:
                diff.append("Removed lines:")
                diff.extend(f"- {line}" for line in sorted(removed))
            if added:
                diff.append("Added lines:")
                diff.extend(f"+ {line}" for line in sorted(added))
            
            return '\n'.join(diff) if diff else None
        return None
    
    def get_config(self, command: typing.Optional[str] = None) -> str:
        """
        Get configuration using Scrapli
        """
        if command:
            _, send_command = _get_scrapli_tasks()
            result = self.task.run(task=send_command, command=command)
        else:
            return self._get_running_config()
        
        if not result.failed:
            return result.result
        else:
            raise Exception(f"Failed to get configuration: {result.result}")
    
    def send_command(self, command: str) -> str:
        """
        Send a command using Scrapli
        """
        _, send_command = _get_scrapli_tasks()
        result = self.task.run(task=send_command, command=command)
        
        if not result.failed:
            return result.result
        else:
            raise Exception(f"Command failed: {result.result}")