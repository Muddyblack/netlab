#
# Unit tests for the 'netlab node' command (command-line parsing, action mapping and the
# containerlab provider hook). No lab is started: the external command runner is mocked.
#
import typing
from unittest import mock

import pytest

from netsim import data
from netsim.cli import node
from netsim.providers.clab import Containerlab


def _topology() -> typing.Any:
  return data.get_box({
    'name': 'lab',
    'defaults': { 'providers': { 'clab': { 'config': 'clab.yml', 'lab_prefix': 'clab' }}},
    'nodes': { 'r1': { 'name': 'r1' }}})

def test_parser_rejects_unknown_action() -> None:
  with pytest.raises(SystemExit):
    node.node_parse(['r1','explode'])

def test_parser_accepts_actions() -> None:
  for action in ['up','down','restart','pause','unpause']:
    args = node.node_parse(['r1,r2',action])
    assert args.node == 'r1,r2' and args.action == action

@pytest.mark.parametrize('action,c_action', [('up','start'),('down','stop'),('restart','restart')])
def test_clab_uses_containerlab_for_up_down_restart(action: str, c_action: str) -> None:
  with mock.patch('netsim.providers.clab.external_commands.run_command',return_value=True) as run:
    clab = Containerlab('clab',data.get_empty_box())
    topo = _topology()
    assert clab.control_node(topo.nodes.r1,topo,action) is True
  run.assert_called_once()
  assert run.call_args.args[0] == ['containerlab',c_action,'-t','clab.yml','--node','r1']

@pytest.mark.parametrize('action', ['pause','unpause'])
def test_clab_uses_docker_for_pause(action: str) -> None:
  with mock.patch('netsim.providers.clab.external_commands.run_command',return_value=True) as run:
    clab = Containerlab('clab',data.get_empty_box())
    topo = _topology()
    assert clab.control_node(topo.nodes.r1,topo,action) is True
  assert run.call_args.args[0] == ['docker',action,'clab-lab-r1']

def test_clab_reports_failure() -> None:
  with mock.patch('netsim.providers.clab.external_commands.run_command',return_value=False):
    clab = Containerlab('clab',data.get_empty_box())
    topo = _topology()
    assert clab.control_node(topo.nodes.r1,topo,'restart') is False

def test_clab_status_reports_paused_and_stopped_nodes() -> None:
  docker_ps = '\n'.join([
    '{"Names":"clab-lab-r1","Status":"Up 2 minutes (Paused)","Image":"frr"}',
    '{"Names":"clab-lab-r2","Status":"Exited (137) 5 seconds ago","Image":"frr"}'])
  with mock.patch('netsim.providers.clab.external_commands.run_command',return_value=docker_ps) as run:
    stat = Containerlab('clab',data.get_empty_box()).get_lab_status({})
  assert 'ps -a' in run.call_args.args[0]
  assert stat['clab-lab-r1'].status == 'Up 2 minutes (Paused)'
  assert stat['clab-lab-r2'].status.startswith('Exited')
