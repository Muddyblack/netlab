#
# Nornir integration for netlab
#
# This module provides an alternative configuration deployment mechanism
# using Nornir instead of Ansible for improved performance
#

from .inventory import AnsibleInventoryAdapter
from .tasks import deploy_config, render_template, deploy_custom_config

__all__ = ['AnsibleInventoryAdapter', 'deploy_config', 'render_template', 'deploy_custom_config']