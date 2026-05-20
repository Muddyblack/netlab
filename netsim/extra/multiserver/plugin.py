"""
multiserver plugin — split a netlab topology across multiple physical servers.

Generates per-server containerlab topology files with cross-server VXLAN links.
See docs/plugins/multiserver.md for usage, examples, and configuration reference.
"""

import os
import pickle
import shutil
from pathlib import Path

import yaml
from box import Box

from netsim.data import append_to_list
from netsim.utils import log

_execute_after = ["fabric", "node.clone"]


# ---------------------------------------------------------------------------
#  Hook: init — validate config + register output hook
# ---------------------------------------------------------------------------


def init(topology: Box) -> None:
  ms = topology.get("multiserver", None)
  if not ms:
    return

  # Merge plugin defaults with user config (user values take priority)
  defaults = topology.defaults.get("multiserver", Box({}))
  topology.multiserver = defaults + ms
  ms = topology.multiserver
  servers = ms.get("servers", [])

  provider = topology.get("provider", "") or topology.defaults.get("provider", "")
  if provider and provider != "clab":
    log.error(
      f'multiserver plugin currently supports only the "clab" provider, not "{provider}"',
      log.IncorrectValue,
      "multiserver",
      more_hints=["libvirt and virtualbox support may be added in a future release"],
    )
    return

  if not servers:
    log.error('multiserver plugin requires a "servers" list', log.MissingValue, "multiserver")
    return

  if len(servers) < 2:
    log.error("multiserver plugin requires at least 2 servers", log.IncorrectValue, "multiserver")
    return

  _validate_servers(servers)
  log.exit_on_error()

  # Register the output hook so netlab create calls our output() function
  append_to_list(topology.defaults.netlab.create, "plugin", "multiserver")


# ---------------------------------------------------------------------------
#  Hook: post_transform — resolve server assignments, classify links
# ---------------------------------------------------------------------------


def post_transform(topology: Box) -> None:
  ms = topology.get("multiserver", None)
  if not ms:
    return

  server_map = {s.id: s for s in ms.servers}
  replicated = _resolve_replicated(ms, topology)
  assignment = _resolve_assignments(ms.servers, topology)

  unassigned = {n for n in topology.nodes if n not in assignment and n not in replicated}
  if unassigned:
    if ms.get("assignment", "explicit") == "explicit":
      log.error(
        f"Nodes not assigned to any server: {', '.join(sorted(unassigned))}",
        log.MissingValue,
        "multiserver",
        more_hints=[
          "Assign nodes via multiserver.servers[].groups or .members",
          "Or set multiserver.assignment: auto for round-robin distribution",
        ],
      )
    else:
      _auto_distribute(unassigned, server_map, assignment, topology)

  log.exit_on_error()

  vni_base = ms.vxlan.get("vni_base", 10000)
  cross_count = _classify_links(topology, assignment, replicated, vni_base)
  log.exit_on_error()

  topology._multiserver = Box({
    "assignment": assignment,
    "server_map": server_map,
    "replicated": sorted(replicated),
  })

  _log_assignment_summary(ms, assignment, replicated, topology, vni_base, cross_count)


# ---------------------------------------------------------------------------
#  Hook: output — generate per-server clab.yml + VXLAN scripts
# ---------------------------------------------------------------------------


def output(topology: Box) -> None:
  ms = topology.get("multiserver", None)
  ms_data = topology.get("_multiserver", None)
  if not ms or not ms_data:
    return

  assignment = ms_data.assignment
  server_map = ms_data.server_map
  vxlan_cfg = ms.vxlan
  out_tpl = ms.get("output_dir", "server-{server_id}")

  replicated = set(ms_data.get("replicated", []))
  server_folders = []

  for server in ms.servers:
    sid = server.id
    local_nodes = {n for n, s in assignment.items() if s == sid} | replicated
    if not local_nodes:
      continue

    out_dir = out_tpl.format(name=topology.name, server_id=sid)
    server_folders.append((out_dir, local_nodes))

    if Path(out_dir).exists():
      shutil.rmtree(out_dir)
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    clab_dict, vxlan_tunnels = _build_server_clab(topology, local_nodes, sid, server_map, vxlan_cfg)

    # Write clab.yml
    with open(Path(out_dir) / "clab.yml", "w") as f:
      yaml.dump(clab_dict, f, default_flow_style=False, sort_keys=False, indent=2)

    # Write filtered snapshot so 'netlab up --snapshot' works per-server
    _write_server_snapshot(topology, local_nodes, out_dir)

    # Generate VXLAN setup/teardown scripts for bridge tunnels
    if vxlan_tunnels:
      dev = server.get("vxlan_dev", "") or vxlan_cfg.get("dev", "")
      if not dev:
        log.error(
          f"Server {sid} has multi-access cross-server links but no VXLAN device is configured",
          log.MissingValue,
          "multiserver",
          more_hints=["Set multiserver.vxlan.dev or multiserver.servers[].vxlan_dev"],
        )
        continue
      _write_vxlan_scripts(out_dir, vxlan_tunnels, dev)

    link_count = len(clab_dict.get("topology", {}).get("links", []))
    vx_count = len(vxlan_tunnels)
    parts = [f"{len(local_nodes)} nodes", f"{link_count} links"]
    if vx_count:
      parts.append(f"{vx_count} VXLAN tunnels")
    log.info(f"Server {sid}: {out_dir}/ — {', '.join(parts)}", module="multiserver")

  # Register atexit handler to copy node_files, host_vars, etc. into each server
  # folder after netlab writes all output files.
  if server_folders:
    import atexit
    atexit.register(_distribute_files_atexit, os.getcwd(), server_folders)


def _distribute_files_atexit(lab_folder: str, server_folders: list) -> None:
  """Distribute generated files"""
  lab_path = Path(lab_folder)
  nf_dir = lab_path / "node_files"
  hv_dir = lab_path / "host_vars"
  server_names = {Path(sf).name for sf, _ in server_folders}

  for sf, local_nodes in server_folders:
    sf_path = Path(sf)
    if not sf_path.is_dir():
      continue

    # node_files: per-node dirs + shared files (names starting with -)
    if nf_dir.is_dir():
      dst_nf = sf_path / "node_files"
      dst_nf.mkdir(exist_ok=True)
      for item in nf_dir.iterdir():
        if item.name in local_nodes or item.name.startswith("-"):
          _copy_if_missing(item, dst_nf / item.name)

    # host_vars: per-node only
    if hv_dir.is_dir():
      dst_hv = sf_path / "host_vars"
      dst_hv.mkdir(exist_ok=True)
      for item in hv_dir.iterdir():
        if item.name in local_nodes:
          _copy_if_missing(item, dst_hv / item.name)

    # Copy all other subdirectories (e.g. group_vars, templates, monitoring)
    # excluding server folders, node_files, host_vars, and python/git metadata.
    skip = server_names | {"node_files", "host_vars", "__pycache__", ".git"}
    for item in lab_path.iterdir():
      if not item.is_dir() or item.name in skip:
        continue
      # Only copy grafana directory if this server hosts the grafana node
      if item.name == "grafana" and "grafana" not in local_nodes:
        continue
      _copy_if_missing(item, sf_path / item.name)

    # Ansible inventory and config
    for fname in ("ansible.cfg", "hosts.yml"):
      src = lab_path / fname
      if src.exists():
        _copy_if_missing(src, sf_path / fname)


def _copy_if_missing(src: Path, dst: Path) -> None:
  if dst.exists():
    return
  try:
    if src.is_dir():
      shutil.copytree(src, dst)
    else:
      shutil.copy2(src, dst)
  except Exception:
    pass


# ===========================================================================
#  Internal helpers — post_transform
# ===========================================================================


def _validate_servers(servers: list) -> None:
  seen_ids: set = set()
  for idx, s in enumerate(servers):
    if "id" not in s:
      log.error(f'Server entry #{idx + 1} missing required "id" field', log.MissingValue, "multiserver")
      continue
    if "host" not in s:
      log.error(f'Server {s.id} missing required "host" field', log.MissingValue, "multiserver")
      continue
    if s.id in seen_ids:
      log.error(f"Duplicate server id {s.id}", log.IncorrectValue, "multiserver")
    seen_ids.add(s.id)


def _resolve_replicated(ms: Box, topology: Box) -> set:
  replicated: set = set()
  for entry in ms.get("replicate", []):
    if entry in topology.nodes:
      replicated.add(entry)
    elif entry in topology.get("groups", {}):
      for member in topology.groups[entry].get("members", []):
        replicated.add(member)
    else:
      log.error(f'multiserver.replicate: "{entry}" is not a node or group', log.IncorrectValue, "multiserver")
  return replicated


def _resolve_assignments(servers: list, topology: Box) -> dict:
  assignment: dict = {}
  for server in servers:
    for gname in server.get("groups", []):
      grp = topology.get("groups", {}).get(gname, None)
      if grp is None:
        log.error(f'Server {server.id} references unknown group "{gname}"', log.IncorrectValue, "multiserver")
        continue
      for member in grp.get("members", []):
        if member in assignment and assignment[member] != server.id:
          log.error(
            f"Node {member} assigned to both server {assignment[member]} and {server.id}",
            log.IncorrectValue,
            "multiserver",
          )
        assignment[member] = server.id

    for member in server.get("members", []):
      if member not in topology.nodes:
        log.error(f'Server {server.id} references unknown node "{member}"', log.IncorrectValue, "multiserver")
        continue
      if member in assignment and assignment[member] != server.id:
        log.error(
          f"Node {member} assigned to both server {assignment[member]} and {server.id}",
          log.IncorrectValue,
          "multiserver",
        )
      assignment[member] = server.id

  return assignment


def _auto_distribute(unassigned: set, server_map: dict, assignment: dict, topology: Box) -> None:
  """Distribute unassigned nodes across servers, keeping netlab groups together."""
  sorted_sids = sorted(server_map.keys())
  counts = {sid: sum(1 for s in assignment.values() if s == sid) for sid in sorted_sids}

  # Build group buckets: keep group members together, distribute largest groups first
  claimed: set = set()
  group_buckets: list = []
  for gdata in topology.get("groups", {}).values():
    members = [m for m in gdata.get("members", []) if m in unassigned and m not in claimed]
    if members:
      group_buckets.append(members)
      claimed.update(members)
  group_buckets.sort(key=lambda g: -len(g))

  for members in group_buckets:
    target = min(sorted_sids, key=lambda s: counts[s])
    for m in members:
      assignment[m] = target
    counts[target] += len(members)

  # Remaining ungrouped nodes: one by one to least-loaded server
  for name in sorted(unassigned - claimed):
    target = min(sorted_sids, key=lambda s: counts[s])
    assignment[name] = target
    counts[target] += 1


def _classify_links(topology: Box, assignment: dict, replicated: set, vni_base: int) -> int:
  """Assign _ms metadata to each link; return the number of cross-server links."""
  vni = vni_base
  for link in topology.links:
    link_servers = {
      assignment[i.node]
      for i in link.get("interfaces", [])
      if i.node not in replicated and i.node in assignment
    }
    if len(link_servers) > 1:
      link._ms = Box({"cross": True, "vni": vni, "servers": sorted(link_servers)})
      vni += 1
    else:
      link._ms = Box({"cross": False, "servers": sorted(link_servers)})

  if vni > 16777215:
    log.error(f"VXLAN VNI overflow: {vni} exceeds 24-bit maximum (16777215)", log.IncorrectValue, "multiserver")

  return vni - vni_base


def _log_assignment_summary(
  ms: Box, assignment: dict, replicated: set, topology: Box, vni_base: int, cross_count: int
) -> None:
  for server in ms.servers:
    sid = server.id
    server_nodes = sorted(n for n, s in assignment.items() if s == sid)
    n = len(server_nodes)

    server_groups = []
    for gname, gdata in topology.get("groups", {}).items():
      members = gdata.get("members", [])
      if not members:
        continue
      on_this = [m for m in members if assignment.get(m) == sid]
      assigned = [m for m in members if m in assignment]
      if on_this and len(on_this) == len(assigned):
        server_groups.append(gname)

    log.info(f"Server {sid} ({server.host}): {n} nodes", module="multiserver")
    if server_groups:
      preview = server_groups[:8]
      suffix = f" ... +{len(server_groups) - 8} more" if len(server_groups) > 8 else ""
      log.info(f"  groups: {', '.join(preview)}{suffix}", module="multiserver")
    if n <= 20:
      log.info(f"  nodes:  {', '.join(server_nodes)}", module="multiserver")
    else:
      log.info(f"  nodes:  {', '.join(server_nodes[:6])} ... +{n - 6} more", module="multiserver")

  if replicated:
    log.info(f"Replicated on all servers: {', '.join(sorted(replicated))}", module="multiserver")
  if cross_count:
    log.info(
      f"{cross_count} cross-server links (VNI {vni_base}–{vni_base + cross_count - 1})", module="multiserver"
    )


# ===========================================================================
#  Internal helpers — clab.yml generation
# ===========================================================================


def _to_plain(obj: object) -> object:
  """Convert Box/BoxList to plain dict/list for clean YAML serialization."""
  if isinstance(obj, Box):
    return {k: _to_plain(v) for k, v in obj.items()}
  if isinstance(obj, list):
    return [_to_plain(v) for v in obj]
  return obj


def _intf_clab_name(intf: Box) -> str:
  """Containerlab interface name for a node interface."""
  return intf.get("clab", {}).get("name", "") or intf.get("ifname", "")


def _build_clab_node(nname: str, ndata: Box, topology: Box) -> dict:
  """Reconstruct a clab.yml node entry from the transformed topology data."""
  entry: dict = {}
  clab = ndata.get("clab", Box({}))

  # Management IPs
  nm = clab.get("network-mode", "")
  if nm != "none":
    if ndata.get("mgmt", {}).get("ipv4"):
      entry["mgmt-ipv4"] = str(ndata.mgmt.ipv4)
    if ndata.get("mgmt", {}).get("ipv6"):
      entry["mgmt-ipv6"] = str(ndata.mgmt.ipv6)

  kind = clab.get("kind", "") or ndata.get("device", "")
  entry["kind"] = kind
  if kind == "linux" and "restart-policy" not in clab:
    entry["restart-policy"] = "no"

  # Pass through standard clab node attributes
  special = set(topology.defaults.providers.clab.get("node_config_special", []))
  for attr in topology.defaults.providers.clab.get("attributes", {}).get("node", {}).get("_keys", []):
    if attr in clab and attr not in special:
      entry[attr] = _to_plain(clab[attr])

  # srl-agents goes under extras: (matches clab.j2 template)
  if "srl-agents" in clab:
    entry["extras"] = {"srl-agents": _to_plain(clab["srl-agents"])}

  entry["image"] = str(clab.get("image", "") or ndata.get("box", ""))
  entry["runtime"] = str(clab.get("runtime", "") or topology.defaults.providers.clab.get("runtime", "docker"))

  # Groups
  if "groups" in topology:
    groups = [g for g in topology.groups if nname in topology.groups[g].get("members", [])]
    if groups:
      entry["group"] = ",".join(groups)

  # Binds — keep paths as-is (relative to the server directory).
  # The distribute script copies node_files/ into each server dir,
  # so paths like node_files/r1/... work when running from there.
  if "binds" in clab:
    entry["binds"] = []
    for b in clab.binds:
      bind_str = f"{b.source}:{b.target}"
      if "mode" in b:
        bind_str += f":{b.mode}"
      entry["binds"].append(bind_str)

  # Startup config
  if "startup-config" in clab:
    entry["startup-config"] = str(clab["startup-config"])

  return entry


def _build_server_clab(topology: Box, local_nodes: set, sid: int, server_map: dict, vxlan_cfg: Box) -> tuple:
  """Build the clab.yml dict and VXLAN tunnel list for one server."""
  dstport = vxlan_cfg.get("dstport", 4789)
  multilab_id = topology.defaults.get("multilab", {}).get("id", 0)
  assignment = topology._multiserver.assignment

  clab: dict = {
    "name": topology.name,
    "prefix": str(topology.defaults.providers.clab.get("lab_prefix", "") or ""),
    "mgmt": {
      "network": str(topology.addressing.mgmt.get("_network", "") or "netlab_mgmt"),
      "ipv4-subnet": str(topology.addressing.mgmt.get("ipv4", "172.20.20.0/24")),
    },
    "topology": {
      "nodes": {},
      "links": [],
    },
  }

  mgmt_bridge = topology.addressing.mgmt.get("_bridge", "")
  if mgmt_bridge:
    clab["mgmt"]["bridge"] = str(mgmt_bridge)
  if topology.defaults.addressing.mgmt.get("ipv6"):
    clab["mgmt"]["ipv6-subnet"] = str(topology.defaults.addressing.mgmt.ipv6)

  # --- Nodes ---
  for nname, ndata in topology.nodes.items():
    if ndata.get("unmanaged", False):
      continue
    if nname in local_nodes:
      clab["topology"]["nodes"][nname] = _build_clab_node(nname, ndata, topology)

  # --- Links ---
  bridges_needed: set = set()
  vxlan_tunnels: list = []

  for link in topology.links:
    local_intfs = [i for i in link.get("interfaces", []) if i.node in local_nodes]
    if not local_intfs:
      continue

    is_cross = link.get("_ms", {}).get("cross", False)
    node_count = link.get("node_count", len(link.get("interfaces", [])))

    # ---- Uplink (macvlan) ----
    if link.get("clab", {}).get("uplink", False):
      for intf in local_intfs:
        clab_name = _intf_clab_name(intf)
        clab["topology"]["links"].append({"endpoints": [f"{intf.node}:{clab_name}", f"macvlan:{link.clab.uplink}"]})
      continue

    # ---- Fully local link ----
    if not is_cross:
      _render_local_link(clab, link, local_intfs, node_count, bridges_needed, multilab_id, topology)
      continue

    # ---- Cross-server P2P (clab native VXLAN) ----
    if node_count == 2:
      _render_p2p_vxlan(clab, link, sid, server_map, local_intfs, assignment, dstport)
      continue

    # ---- Cross-server multi-access (bridge + host VXLAN) ----
    _render_bridge_vxlan(
      clab,
      link,
      sid,
      server_map,
      local_intfs,
      assignment,
      bridges_needed,
      vxlan_tunnels,
      dstport,
      multilab_id,
      topology,
    )

  # --- Bridge nodes ---
  bridge_type = str(topology.defaults.providers.clab.get("bridge_type", "bridge"))
  for brname in sorted(bridges_needed):
    clab["topology"]["nodes"][brname] = {"kind": bridge_type}

  if not clab["topology"]["links"]:
    del clab["topology"]["links"]

  return clab, vxlan_tunnels


def _render_local_link(
  clab: dict, link: Box, local_intfs: list, node_count: int, bridges_needed: set, multilab_id: int, topology: Box
) -> None:
  """Render a fully-local link (all endpoints on the same server)."""

  # Stub link
  if node_count == 1 and local_intfs:
    intf = local_intfs[0]
    clab["topology"]["links"].append(
      {
        "type": "dummy",
        "endpoint": {"node": intf.node, "interface": _intf_clab_name(intf)},
      }
    )
    return

  # P2P link
  if node_count == 2:
    endpoints = [f"{i.node}:{_intf_clab_name(i)}" for i in local_intfs]
    if len(endpoints) == 2:
      clab["topology"]["links"].append({"endpoints": endpoints})
    return

  # Multi-access link (bridge)
  if node_count > 2 and link.get("bridge"):
    bridge = link.bridge
    if not link.get("clab", {}).get("external_bridge", False):
      bridges_needed.add(bridge)
    for intf in local_intfs:
      ndata = topology.nodes[intf.node]
      bridge_intf = f"bni{multilab_id}n{ndata.id}i{intf.ifindex}"
      clab["topology"]["links"].append(
        {
          "endpoints": [
            f"{intf.node}:{_intf_clab_name(intf)}",
            f"{bridge}:{bridge_intf}",
          ]
        }
      )


def _render_p2p_vxlan(
  clab: dict, link: Box, local_sid: int, server_map: dict, local_intfs: list, assignment: dict, dstport: int
) -> None:
  """Render a P2P cross-server link as a containerlab native VXLAN endpoint."""
  if not local_intfs:
    return

  vni = link._ms.vni
  local_intf = local_intfs[0]

  # Find the remote server
  remote_sid = None
  for intf in link.get("interfaces", []):
    s = assignment.get(intf.node)
    if s is not None and s != local_sid:
      remote_sid = s
      break

  if remote_sid is None:
    return

  clab_name = _intf_clab_name(local_intf)
  clab["topology"]["links"].append(
    {
      "endpoints": [
        f"{local_intf.node}:{clab_name}",
        f"host:vx{vni}",
      ],
      "type": "vxlan",
      "remote": str(server_map[remote_sid].host),
      "vni": vni,
      "udp-port": dstport,
    }
  )


def _render_bridge_vxlan(
  clab: dict,
  link: Box,
  local_sid: int,
  server_map: dict,
  local_intfs: list,
  assignment: dict,
  bridges_needed: set,
  vxlan_tunnels: list,
  dstport: int,
  multilab_id: int,
  topology: Box,
) -> None:
  """Render a multi-access cross-server link: local bridge + host VXLAN tunnels."""
  vni = link._ms.vni
  bridge = link.get("bridge", f"br{link.linkindex}")

  if not link.get("clab", {}).get("external_bridge", False):
    bridges_needed.add(bridge)

  # Local node-to-bridge connections
  for intf in local_intfs:
    ndata = topology.nodes[intf.node]
    bridge_intf = f"bni{multilab_id}n{ndata.id}i{intf.ifindex}"
    clab["topology"]["links"].append(
      {
        "endpoints": [
          f"{intf.node}:{_intf_clab_name(intf)}",
          f"{bridge}:{bridge_intf}",
        ]
      }
    )

  # VXLAN tunnels to each remote server that has endpoints on this link
  remote_sids = {assignment[i.node] for i in link.get("interfaces", []) if assignment.get(i.node) not in (None, local_sid)}
  for rsid in sorted(remote_sids):
    vxlan_tunnels.append(
      {
        "bridge": bridge,
        "vni": vni,
        "remote": str(server_map[rsid].host),
        "dstport": dstport,
        "remote_id": rsid,
      }
    )


# ---------------------------------------------------------------------------
#  File operations
# ---------------------------------------------------------------------------


def _write_server_snapshot(topology: Box, local_nodes: set, out_dir: str) -> None:
  """Write a filtered netlab snapshot for this server's nodes only.

  Allows 'netlab up --snapshot' to work from a per-server directory.
  make_paths_absolute() is called here explicitly because output() hooks run
  before create.py does it — without it the snapshot is missing f_files/f_tasks/f_dirs.
  """
  from netsim import __version__
  from netsim.augment.config import make_paths_absolute
  from netsim.augment.topology import cleanup_topology

  topo_copy = Box(topology, box_dots=True)

  # Filter nodes to only those on this server
  topo_copy.nodes = Box({n: v for n, v in topo_copy.nodes.items() if n in local_nodes}, box_dots=True)

  # Filter links to only those with at least one local endpoint
  topo_copy.links = [l for l in topo_copy.links if any(i.node in local_nodes for i in l.get("interfaces", []))]

  # Expand paths (add f_files / f_tasks / f_dirs computed keys).
  make_paths_absolute(topo_copy.defaults.paths)

  # Remove prefix generators and serialize
  cleaned = cleanup_topology(topo_copy)
  topodict = cleaned.to_dict()
  topodict["_netlab_version"] = __version__

  with open(Path(out_dir) / "netlab.snapshot.pickle", "wb") as f:
    pickle.dump(topodict, f)


def _write_vxlan_scripts(out_dir: str, tunnels: list, dev: str) -> None:
  """Generate bash scripts to create/destroy host-level VXLAN tunnels."""

  setup = [
    "#!/bin/bash",
    "# VXLAN tunnel setup — generated by netlab multiserver plugin",
    "# Run AFTER:  sudo clab deploy -t clab.yml",
    "#",
    "# Creates host-level VXLAN tunnels and attaches them to containerlab bridges.",
    "# These tunnels carry multi-access (bridged) cross-server traffic.",
    "set -e",
    "",
  ]

  teardown = [
    "#!/bin/bash",
    "# VXLAN tunnel teardown — generated by netlab multiserver plugin",
    "# Run BEFORE: sudo clab destroy -t clab.yml",
    "set -e",
    "",
  ]

  seen: set = set()
  for t in tunnels:
    vx_name = f"vxlan{t['vni']}"
    key = (vx_name, t["remote"])
    if key in seen:
      continue
    seen.add(key)

    setup.extend(
      [
        f"# VNI {t['vni']} -> {t['remote']} (server {t['remote_id']}) via bridge {t['bridge']}",
        f"ip link add {vx_name} type vxlan id {t['vni']} remote {t['remote']} dev {dev} dstport {t['dstport']}",
        f"ip link set {vx_name} master {t['bridge']}",
        f"ip link set {vx_name} up",
        f'echo "  {vx_name} -> {t["bridge"]} (remote {t["remote"]})"',
        "",
      ]
    )

    teardown.append(f'ip link del {vx_name} 2>/dev/null && echo "  deleted {vx_name}" || true')

  setup.append('echo "VXLAN setup complete."')
  teardown.extend(["", 'echo "VXLAN teardown complete."'])

  for name, lines in [("vxlan-setup.sh", setup), ("vxlan-teardown.sh", teardown)]:
    path = Path(out_dir) / name
    path.write_text("\n".join(lines) + "\n")
    os.chmod(path, 0o755)
