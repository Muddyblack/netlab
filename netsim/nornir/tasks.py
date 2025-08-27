#
# Nornir tasks for configuration deployment
#
# This module provides tasks for rendering templates and deploying
# configurations to network devices using Nornir
#

import os
import typing
from pathlib import Path

from box import Box
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from nornir.core.task import Result, Task

from ..utils import log, files as _files
from .drivers import get_driver


def render_template(task: Task, template_path: str, **kwargs) -> Result:
    """
    Render a Jinja2 template with host variables
    
    Args:
        task: Nornir task object
        template_path: Path to the Jinja2 template
        **kwargs: Additional variables to pass to the template
        
    Returns:
        Result object with rendered configuration
    """
    host = task.host
    
    # Prepare template variables
    template_vars = {
        'inventory_hostname': host.name,
        'ansible_host': host.hostname,
        **host.data,  # All host variables from Ansible inventory
        **kwargs
    }
    
    # Set up Jinja2 environment
    template_dir = os.path.dirname(template_path)
    template_name = os.path.basename(template_path)
    
    env = Environment(
        loader=FileSystemLoader(template_dir),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True
    )
    
    try:
        template = env.get_template(template_name)
        rendered = template.render(**template_vars)
        
        return Result(
            host=task.host,
            result=rendered,
            changed=False
        )
    except Exception as e:
        return Result(
            host=task.host,
            failed=True,
            exception=e,
            result=f"Failed to render template: {str(e)}"
        )


def deploy_config(task: Task, config: str, replace: bool = False,
                 commit: bool = True, diff: bool = True) -> Result:
    """
    Deploy configuration to a network device
    
    Args:
        task: Nornir task object
        config: Configuration to deploy
        replace: Replace entire configuration (default: False - merge)
        commit: Commit configuration (default: True)
        diff: Show configuration diff (default: True)
        
    Returns:
        Result object with deployment status
    """
    host = task.host
    
    # Get the appropriate driver for this platform
    driver_class = get_driver(host.platform)
    if not driver_class:
        return Result(
            host=task.host,
            failed=True,
            result=f"No driver available for platform {host.platform}"
        )
    
    try:
        # Initialize driver with host connection options
        driver = driver_class(task)
        
        # Connect to device
        driver.connect()
        
        # Deploy configuration
        if replace:
            result = driver.replace_config(config, commit=commit)
        else:
            result = driver.merge_config(config, commit=commit)
        
        # Get diff if requested
        config_diff = None
        if diff and hasattr(driver, 'get_diff'):
            config_diff = driver.get_diff()
        
        # Close connection
        driver.close()
        
        return Result(
            host=task.host,
            changed=result.get('changed', True),
            diff=config_diff,
            result=result
        )
        
    except Exception as e:
        return Result(
            host=task.host,
            failed=True,
            exception=e,
            result=f"Failed to deploy configuration: {str(e)}"
        )


def find_custom_template(task: Task, template_name: str,
                        search_paths: typing.List[str]) -> typing.Optional[str]:
    """
    Find a custom configuration template using netlab's search paths
    
    Args:
        task: Nornir task object
        template_name: Name of the template to find
        search_paths: List of paths to search in
        
    Returns:
        Full path to the template or None if not found
    """
    host = task.host
    device_type = host.data.get('netlab_device_type', host.platform)
    provider = host.data.get('netlab_provider', '')
    
    # Build list of possible template names
    template_variations = []
    
    if template_name.endswith('.j2'):
        template_variations.append(template_name)
    else:
        # Add variations based on device type and provider
        template_variations.extend([
            f"{template_name}.j2",
            f"{template_name}.{host.name}.j2",
            f"{template_name}.{device_type}.j2",
            f"{template_name}.{provider}.j2",
            f"{template_name}.{device_type}.{provider}.j2"
        ])
    
    # Search for template
    for path in search_paths:
        for variation in template_variations:
            full_path = os.path.join(path, variation)
            if os.path.exists(full_path):
                return full_path
    
    return None


def deploy_custom_config(task: Task, template_name: str,
                        search_paths: typing.List[str],
                        **kwargs) -> Result:
    """
    High-level task that finds, renders, and deploys a custom configuration
    
    Args:
        task: Nornir task object
        template_name: Name of the configuration template
        search_paths: List of paths to search for templates
        **kwargs: Additional variables for template rendering
        
    Returns:
        Result object with deployment status
    """
    # Find the template
    template_path = find_custom_template(task, template_name, search_paths)
    if not template_path:
        return Result(
            host=task.host,
            failed=True,
            result=f"Cannot find template {template_name} for device {task.host.name}"
        )
    
    # Render the template
    render_result = task.run(
        task=render_template,
        template_path=template_path,
        **kwargs
    )
    
    if render_result.failed:
        return render_result
    
    # Deploy the configuration
    config = render_result.result
    deploy_result = task.run(
        task=deploy_config,
        config=config,
        diff=True
    )
    
    return deploy_result


def collect_device_config(task: Task, command: typing.Optional[str] = None) -> Result:
    """
    Collect running configuration from a device
    
    Args:
        task: Nornir task object
        command: Optional command to run (defaults to platform-specific)
        
    Returns:
        Result object with device configuration
    """
    host = task.host
    
    # Get the appropriate driver
    driver_class = get_driver(host.platform)
    if not driver_class:
        return Result(
            host=task.host,
            failed=True,
            result=f"No driver available for platform {host.platform}"
        )
    
    try:
        driver = driver_class(task)
        driver.connect()
        
        # Get configuration
        if hasattr(driver, 'get_config'):
            config = driver.get_config(command=command)
        else:
            config = driver.send_command(command or 'show running-config')
        
        driver.close()
        
        return Result(
            host=task.host,
            result=config
        )
        
    except Exception as e:
        return Result(
            host=task.host,
            failed=True,
            exception=e,
            result=f"Failed to collect configuration: {str(e)}"
        )