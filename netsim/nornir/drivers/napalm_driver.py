#
# NAPALM driver for Nornir configuration deployment
#

import typing
from nornir_napalm.plugins.tasks import napalm_configure, napalm_get
from .base import BaseDriver


class NapalmDriver(BaseDriver):
    """
    Driver using NAPALM for configuration deployment
    """
    
    def __init__(self, task):
        super().__init__(task)
        self._diff = None
    
    def connect(self) -> None:
        """
        NAPALM handles connections internally, so this is a no-op
        """
        pass
    
    def close(self) -> None:
        """
        NAPALM handles connection cleanup internally
        """
        pass
    
    def merge_config(self, config: str, commit: bool = True) -> dict:
        """
        Merge configuration using NAPALM
        """
        result = self.task.run(
            task=napalm_configure,
            configuration=config,
            replace=False,
            commit=commit,
            dry_run=not commit
        )
        
        if not result.failed:
            self._diff = result.result.get('diff', '')
            return {
                'changed': bool(self._diff),
                'diff': self._diff
            }
        else:
            raise Exception(f"Configuration merge failed: {result.result}")
    
    def replace_config(self, config: str, commit: bool = True) -> dict:
        """
        Replace configuration using NAPALM
        """
        result = self.task.run(
            task=napalm_configure,
            configuration=config,
            replace=True,
            commit=commit,
            dry_run=not commit
        )
        
        if not result.failed:
            self._diff = result.result.get('diff', '')
            return {
                'changed': bool(self._diff),
                'diff': self._diff
            }
        else:
            raise Exception(f"Configuration replace failed: {result.result}")
    
    def get_diff(self) -> typing.Optional[str]:
        """
        Return the last configuration diff
        """
        return self._diff
    
    def get_config(self, command: typing.Optional[str] = None) -> str:
        """
        Get running configuration using NAPALM
        """
        result = self.task.run(
            task=napalm_get,
            getters=["config"]
        )
        
        if not result.failed:
            return result.result['config']['running']
        else:
            raise Exception(f"Failed to get configuration: {result.result}")