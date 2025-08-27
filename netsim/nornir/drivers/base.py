#
# Base driver class for Nornir configuration deployment
#

import typing
from abc import ABC, abstractmethod
from nornir.core.task import Task


class BaseDriver(ABC):
    """
    Abstract base class for platform-specific configuration drivers
    """
    
    def __init__(self, task: Task):
        """
        Initialize driver with Nornir task
        
        Args:
            task: Nornir task object containing host information
        """
        self.task = task
        self.host = task.host
        self.connection = None
    
    @abstractmethod
    def connect(self) -> None:
        """
        Establish connection to the device
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """
        Close connection to the device
        """
        pass
    
    @abstractmethod
    def merge_config(self, config: str, commit: bool = True) -> dict:
        """
        Merge configuration with existing device configuration
        
        Args:
            config: Configuration to merge
            commit: Whether to commit the configuration
            
        Returns:
            Dictionary with operation result
        """
        pass
    
    @abstractmethod
    def replace_config(self, config: str, commit: bool = True) -> dict:
        """
        Replace entire device configuration
        
        Args:
            config: New configuration
            commit: Whether to commit the configuration
            
        Returns:
            Dictionary with operation result
        """
        pass
    
    def get_diff(self) -> typing.Optional[str]:
        """
        Get configuration diff (if available)
        
        Returns:
            Configuration diff or None
        """
        return None
    
    def get_config(self, command: typing.Optional[str] = None) -> str:
        """
        Get running configuration from device
        
        Args:
            command: Optional command to get config
            
        Returns:
            Device configuration
        """
        raise NotImplementedError("get_config not implemented for this driver")
    
    def send_command(self, command: str) -> str:
        """
        Send a command to the device
        
        Args:
            command: Command to execute
            
        Returns:
            Command output
        """
        raise NotImplementedError("send_command not implemented for this driver")