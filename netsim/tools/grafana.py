#
# Grafana / Prometheus monitoring stack -- configuration renderer
#
# This module renders two configuration files that cannot be produced with a
# plain Jinja2 template:
#
# * prometheus.yml   -- scrape targets are grouped by Prometheus job, which is
#                       awkward to express in Jinja2 but trivial in Python.
# * netlab-overview.json -- the default Grafana dashboard is shipped verbatim.
#                       Grafana legend formats use `{{ ... }}` syntax that would
#                       collide with Jinja2, so the file is copied as-is.
#

from pathlib import Path

from box import Box

from ..utils import log
from . import _ToolOutput

CADVISOR_PORT = 8080
DEFAULT_CLAB_PREFIX = "clab"
DEFAULT_METRICS_PATH = "/metrics"
DEFAULT_JOB = "netlab"


def clab_container_name(topology: Box, node: str) -> str:
  """Reconstruct the containerlab container name for a node (used as the
  Prometheus 'instance' label so it lines up with the cAdvisor 'name' label)."""
  prefix = topology.get("defaults.providers.clab.lab_prefix", DEFAULT_CLAB_PREFIX)
  if prefix is None:
    prefix = DEFAULT_CLAB_PREFIX
  return f"{prefix}-{topology.name}-{node}" if prefix else node


def node_scrape_targets(topology: Box) -> list:
  """Collect opt-in node exporters, grouped by (job, metrics_path) so that
  every Prometheus scrape_config has a unique job_name."""
  groups: dict = {}
  for name, ndata in topology.nodes.items():
    gdata = ndata.get("grafana", {})
    port = gdata.get("port", None)
    if not port:                                    # No exporter port -> skip the node
      continue

    mgmt_ip = ndata.get("mgmt.ipv4", None) or ndata.get("mgmt.ipv6", None)
    if not mgmt_ip:                                 # Cannot scrape a node without a management address
      continue

    job = gdata.get("job", None) or DEFAULT_JOB
    path = gdata.get("path", None) or DEFAULT_METRICS_PATH
    target = {
        "targets": [f"{mgmt_ip}:{port}"],
        "labels": {
            "instance": clab_container_name(topology, name),
            "node": name,
            "lab": topology.name,
            "device": ndata.device,
        },
    }
    groups.setdefault((job, path), []).append(target)

  scrape_configs = []
  for (job, path), targets in groups.items():
    scrape_configs.append({
        "job_name": job,
        "metrics_path": path,
        "static_configs": targets,
    })
  return scrape_configs


def prometheus_config(topology: Box) -> str:
  lab = topology.name
  scrape_configs = [
      {                                             # cAdvisor: works with zero device configuration
          "job_name": "cadvisor",
          "static_configs": [{
              "targets": [f"{lab}_cadvisor:{CADVISOR_PORT}"],
              "labels": {"lab": lab},
          }],
      },
      {                                             # Prometheus self-monitoring
          "job_name": "prometheus",
          "static_configs": [{
              "targets": ["localhost:9090"],
              "labels": {"lab": lab},
          }],
      },
  ]
  scrape_configs += node_scrape_targets(topology)

  cfg = Box({
      "global": {"scrape_interval": "15s", "evaluation_interval": "15s"},
      "scrape_configs": scrape_configs,
  })
  return cfg.to_yaml()


def default_dashboard() -> str:
  dashboard = Path(__file__).parent / "grafana" / "dashboards" / "netlab-overview.json"
  return dashboard.read_text()


class Grafana(_ToolOutput):

  def write(self, topology: Box, fmt: str) -> str:
    if fmt == "prometheus":
      return prometheus_config(topology)
    if fmt == "dashboard-overview":
      return default_dashboard()

    log.error(
        f"Unknown grafana rendering format {fmt}",
        log.IncorrectValue,
        "grafana")
    return ""
