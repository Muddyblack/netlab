(plugin-multiserver)=
# Splitting Topologies Across Multiple Servers

The *multiserver* plugin distributes a single *netlab* topology across multiple physical servers. It assigns nodes to servers, classifies links as local or cross-server, and generates a self-contained containerlab configuration directory for each server with VXLAN-based interconnects.

```eval_rst
.. contents:: Table of Contents
   :depth: 2
   :local:
   :backlinks: none
```

```{warning}
* The *multiserver* plugin requires the **containerlab** provider on all servers.
* Containerlab version >= `0.46` is required for native VXLAN link endpoint support.
* All physical servers must have direct IP reachability (e.g. over a management network or dedicated interconnect).
```

## Using the Plugin

* Add `plugin: [ multiserver ]` to lab topology.
* Define target servers in the **multiserver.servers** list.
* Choose an assignment mode (`explicit` or `auto`) with **multiserver.assignment**.

The plugin runs during `netlab create` and generates self-contained per-server directories (e.g. `server-1/`, `server-2/`) with tailored `clab.yml` files, node configs, and VXLAN scripts ready for deployment.

## Configuring Plugin Parameters

The plugin is configured with the **multiserver** topology-level dictionary that has these parameters:

| Parameter | Type | Meaning |
|-----------|------|---------|
| **assignment** | string | How to assign nodes to servers: `explicit` (default) or `auto` |
| **servers** | list | List of target physical servers |
| **vxlan** | dictionary | Global settings for VXLAN tunnels |
| **replicate** | list | Nodes or groups that must be duplicated on all servers |
| **output_dir** | string | Template for per-server directory names (default: `server-{server_id}`) |

(multiserver-servers)=
### Server Parameters

Each entry in the **multiserver.servers** list supports these parameters:

| Parameter | Type | Meaning |
|-----------|------|---------|
| **id** | integer | Unique identifier for the server (e.g. `1`, `2`) |
| **host** | string | IP address or hostname of the remote server |
| **groups** | list | *netlab* groups whose members are assigned to this server |
| **members** | list | Individual node names assigned to this server |
| **vxlan_dev** | string | Physical interface to bind VXLAN tunnels to on this server |

(multiserver-vxlan)=
### VXLAN Parameters

Global VXLAN settings are specified in the **multiserver.vxlan** dictionary:

| Parameter | Type | Meaning |
|-----------|------|---------|
| **vni_base** | integer | Starting VNI for cross-server links (default: `10000`) |
| **dstport** | integer | UDP destination port for VXLAN traffic (default: `4789`) |
| **dev** | string | Default physical interface to bind VXLAN tunnels (default: `ens33`) |

(multiserver-assignment)=
## Assignment Modes

### Explicit Assignment (Default)

In `explicit` mode, every node must be mapped to a server using the **groups** or **members** attributes of a [server entry](multiserver-servers). Any unassigned node (excluding [replicated nodes](multiserver-replicate)) results in an error.

```yaml
plugin: [ multiserver ]

multiserver:
  assignment: explicit
  servers:
    - id: 1
      host: 192.168.168.128
      groups: [ core ]
      members: [ edge-node ]
    - id: 2
      host: 192.168.168.129
      groups: [ spines, leaves ]
```

### Automatic Assignment

In `auto` mode, nodes that are not explicitly pinned to a server are distributed automatically using a greedy balancing algorithm:

1. Nodes belonging to a *netlab* group are kept together — the entire group is placed on the server that currently has the fewest nodes. Larger groups are placed first for better balance.
2. Remaining ungrouped nodes are assigned one at a time to the least-loaded server.

Nodes already pinned via **groups** or **members** attributes count toward server load, so the algorithm balances around any explicit assignments.

```yaml
plugin: [ multiserver ]

multiserver:
  assignment: auto
  servers:
    - id: 1
      host: 192.168.168.128
    - id: 2
      host: 192.168.168.129
```

```{tip}
You can pin specific nodes or groups to a server in `auto` mode using **groups** and **members** attributes. Only unassigned nodes are auto-distributed.
```

#### Group Granularity

Because auto mode keeps entire groups together on a single server, the granularity of your groups directly affects how evenly nodes are distributed. Define groups at the smallest unit you want to keep on one server.

For example, consider a topology with two sites, each containing five nodes:

```yaml
# BAD: one large group — all 10 nodes land on one server
groups:
  sites:
    members: [ site1-r1, site1-r2, site1-r3, site1-r4, site1-r5,
               site2-r1, site2-r2, site2-r3, site2-r4, site2-r5 ]
```

```yaml
# GOOD: per-site groups — one site per server
groups:
  site1:
    members: [ site1-r1, site1-r2, site1-r3, site1-r4, site1-r5 ]
  site2:
    members: [ site2-r1, site2-r2, site2-r3, site2-r4, site2-r5 ]
  sites:
    members: [ site1-r1, site1-r2, site1-r3, site1-r4, site1-r5,
               site2-r1, site2-r2, site2-r3, site2-r4, site2-r5 ]
```

In the second example the parent `sites` group can still be used for Ansible targeting or shared configuration — it does not affect placement because the child groups (`site1`, `site2`) claim their members first during assignment.

```{note}
Groups are processed in definition order. Child groups defined **before** a parent group will claim their members first, making the parent group a no-op for assignment. Always define fine-grained groups before aggregate groups in your topology.
```

(multiserver-replicate)=
### Replicated Nodes

Nodes listed in **multiserver.replicate** are instantiated on every server. This is useful for infrastructure services that need local access on each physical host — for example, monitoring collectors, route reflectors, or DNS resolvers.

Links connecting to replicated nodes are always treated as local, so traffic between a replicated node and its neighbors never crosses the VXLAN overlay.

```yaml
multiserver:
  assignment: auto
  servers:
    - id: 1
      host: 192.168.168.128
    - id: 2
      host: 192.168.168.129
  replicate: [ prometheus, grafana ]
```

## Complete Example

A minimal two-server topology with explicit assignment:

```yaml
plugin: [ multiserver ]

provider: clab

groups:
  spines:
    members: [ s1, s2 ]
  leaves:
    members: [ l1, l2 ]

nodes:
  s1:
    device: srlinux
  s2:
    device: srlinux
  l1:
    device: srlinux
  l2:
    device: srlinux

links:
  - s1-l1
  - s1-l2
  - s2-l1
  - s2-l2

multiserver:
  assignment: explicit
  servers:
    - id: 1
      host: 192.168.168.128
      groups: [ spines ]
    - id: 2
      host: 192.168.168.129
      groups: [ leaves ]
  vxlan:
    vni_base: 10000
    dev: ens33
```

This places spines on server 1 and leaves on server 2. All four links cross servers and are provisioned as containerlab native VXLAN endpoints.

## Behind the Scenes

When the plugin processes the topology, it classifies links into three categories:

* **Local links** connecting nodes on the same server remain as regular containerlab veth pairs or bridges.
* **Cross-server point-to-point links** are provisioned via containerlab's native VXLAN link endpoints (`type: vxlan` in `clab.yml`).
* **Cross-server multi-access links** use a local Linux bridge on each server, interconnected via host-level VXLAN tunnels configured by generated setup scripts.

Each per-server directory is self-contained and includes:

* A tailored `clab.yml` with only the relevant nodes and cross-server VXLAN interfaces
* A filtered `netlab.snapshot.pickle` for use with `netlab up --snapshot`
* Copies of `node_files/`, `host_vars/`, and Ansible config for only the nodes on that server
* `vxlan-setup.sh` and `vxlan-teardown.sh` scripts (when multi-access VXLAN tunnels are needed)

(multiserver-deployment)=
## Deployment Workflow

**Step 1: Generate configurations** on your workstation:

```bash
netlab create topology.yml
```

The plugin automatically copies all required files into each server directory — no extra bundling step is needed.

**Step 2: Copy server directories to remote hosts** (e.g. via rsync):

```bash
rsync -avz server-1/ user@192.168.168.128:~/lab/server-1/
rsync -avz server-2/ user@192.168.168.129:~/lab/server-2/
```

**Step 3: Deploy on each server** by running the following on each remote host:

```bash
sudo netlab up --snapshot -vv
sudo ./vxlan-setup.sh    # only if multi-access VXLAN tunnels are present
```

```{important}
**Why is `--snapshot` required on remote servers?**

You must run `sudo netlab up --snapshot` on remote servers to load the topology from the pre-generated snapshot (`netlab.snapshot.pickle`) instead of the original `topology.yml`. 

Running with `topology.yml` directly on remote servers will fail because:
1. **Consistency**: Netlab dynamically allocates IP addresses, interface IDs, and VXLAN VNIs. Independent creation runs on different hosts would result in mismatched allocations.
2. **Recursion**: Running `netlab create` on `topology.yml` on the remote hosts would execute the `multiserver` plugin again, causing it to split the topology recursively and generate nested server subdirectories.
```

**Teardown** in reverse order:

```bash
sudo ./vxlan-teardown.sh
sudo clab destroy -t clab.yml
```

## Limitations

* Only the **containerlab** provider is supported. Libvirt and virtualbox topologies cannot be split across servers.
* Cross-server VXLAN tunnels use a flat VNI space starting at **vni_base**. The maximum VNI value is 16777215 (24-bit). Topologies with more than ~16 million cross-server links will fail validation.
* All physical servers must have direct IP reachability — the plugin does not support NAT traversal or relay hosts between servers.
