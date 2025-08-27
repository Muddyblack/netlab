#
# Nornir drivers for different network platforms
#
# This module provides a driver abstraction layer for deploying
# configurations to various network devices
#

import typing

# Import drivers only when they're actually used to avoid import errors
# when dependencies are not installed
_driver_classes = {
    'base': 'netsim.nornir.drivers.base:BaseDriver',
    'napalm': 'netsim.nornir.drivers.napalm_driver:NapalmDriver',
    'scrapli': 'netsim.nornir.drivers.scrapli_driver:ScrapliDriver',
    'linux': 'netsim.nornir.drivers.linux_driver:LinuxDriver',
}

def _lazy_import(module_path: str):
    """Lazy import a class from a module"""
    module_name, class_name = module_path.split(':')
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


# Platform to driver mapping
PLATFORM_DRIVERS = {
    # NAPALM-supported platforms
    'arista_eos': 'napalm',
    'cisco_ios': 'napalm',
    'cisco_iosxr': 'napalm',
    'cisco_nxos': 'napalm',
    'juniper_junos': 'napalm',
    
    # Scrapli-supported platforms
    'cisco_iosxe': 'scrapli',
    'nokia_sros': 'scrapli',
    'nokia_srlinux': 'scrapli',
    
    # Linux-based platforms
    'linux': 'linux',
    'frr': 'linux',
    'cumulus': 'linux',
    'vyos': 'linux',
    'sonic': 'linux',
}


def get_driver(platform: str):
    """
    Get the appropriate driver class for a platform
    
    Args:
        platform: Platform identifier
        
    Returns:
        Driver class or None if not supported
    """
    driver_type = PLATFORM_DRIVERS.get(platform)
    if driver_type and driver_type in _driver_classes:
        return _lazy_import(_driver_classes[driver_type])
    return None


def register_driver(platform: str, driver_class) -> None:
    """
    Register a custom driver for a platform
    
    Args:
        platform: Platform identifier
        driver_class: Driver class to register
    """
    # Register the driver class directly
    class_name = driver_class.__name__
    module_name = driver_class.__module__
    _driver_classes[class_name.lower()] = f"{module_name}:{class_name}"
    PLATFORM_DRIVERS[platform] = class_name.lower()


# Export the lazy-loaded base class
BaseDriver = _lazy_import(_driver_classes['base'])

__all__ = ['BaseDriver', 'get_driver', 'register_driver']