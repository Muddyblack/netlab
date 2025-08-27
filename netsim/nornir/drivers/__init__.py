#
# Nornir drivers for different network platforms
#
# This module provides a driver abstraction layer for deploying
# configurations to various network devices
#

import typing
from .base import BaseDriver
from .napalm_driver import NapalmDriver
from .scrapli_driver import ScrapliDriver
from .linux_driver import LinuxDriver


# Platform to driver mapping
PLATFORM_DRIVERS = {
    # NAPALM-supported platforms
    'arista_eos': NapalmDriver,
    'cisco_ios': NapalmDriver,
    'cisco_iosxr': NapalmDriver,
    'cisco_nxos': NapalmDriver,
    'juniper_junos': NapalmDriver,
    
    # Scrapli-supported platforms
    'cisco_iosxe': ScrapliDriver,
    'nokia_sros': ScrapliDriver,
    'nokia_srlinux': ScrapliDriver,
    
    # Linux-based platforms
    'linux': LinuxDriver,
    'frr': LinuxDriver,
    'cumulus': LinuxDriver,
    'vyos': LinuxDriver,
    'sonic': LinuxDriver,
}


def get_driver(platform: str) -> typing.Optional[typing.Type[BaseDriver]]:
    """
    Get the appropriate driver class for a platform
    
    Args:
        platform: Platform identifier
        
    Returns:
        Driver class or None if not supported
    """
    return PLATFORM_DRIVERS.get(platform)


def register_driver(platform: str, driver_class: typing.Type[BaseDriver]) -> None:
    """
    Register a custom driver for a platform
    
    Args:
        platform: Platform identifier
        driver_class: Driver class to register
    """
    PLATFORM_DRIVERS[platform] = driver_class


__all__ = ['BaseDriver', 'NapalmDriver', 'ScrapliDriver', 'LinuxDriver',
           'get_driver', 'register_driver']