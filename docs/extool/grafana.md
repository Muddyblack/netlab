(tools-grafana)=
# Grafana + Prometheus Monitoring

The *grafana* tool starts a self-contained monitoring stack next to your lab and wires it to the lab management network, so you can watch what your devices are doing without setting anything up yourself.

Enabling the tool starts three containers:

* **cAdvisor** collects per-container CPU, memory, and traffic metrics for every lab node. It needs no device configuration -- the moment the lab is up you get data.
* **Prometheus** scrapes cAdvisor (and, optionally, metrics exporters running on the lab nodes) over the management network. Its scrape targets are generated from your topology.
* **Grafana** displays the data. It ships with a ready-to-use *netlab overview* dashboard, a pre-configured Prometheus data source, and anonymous access, so you just open the URL.

```{tip}
This tool follows the same rules as every other [external tool](tools-intro): it runs as a set of Docker containers, so you have to run your lab on a Linux server with Docker (typically with the *containerlab* provider).
```

## Enabling the Tool

Add two lines to your lab topology:

```
tools:
  grafana:
```

The URLs for Grafana and Prometheus are printed at the end of **netlab up**; you can display them again with **netlab connect grafana** or **netlab status**.

To start Grafana with *every* lab, enable it in your [user defaults](tools-enable-default) (`~/.netlab.yml`):

```
tools.grafana.enabled: True
```

## What You Get Out of the Box

Once the lab is up, open the Grafana URL. The *netlab overview* dashboard shows, for every lab container:

* the number of running containers, total CPU, memory, and fleet traffic;
* CPU, memory, and RX/TX traffic per node;
* a per-node detail section with an interface-level traffic breakdown.

The dashboard filters containers by name using the **Container filter** variable (default `clab-.*`, which matches containerlab node names). Adjust it if you changed the [containerlab naming prefix](clab-prefix).

## Scraping Metrics From the Devices (optional)

cAdvisor gives you resource metrics for free. To also collect *protocol* metrics (OSPF/BGP state, routes, SPF runs...) you need a metrics exporter -- for example [frr_exporter](https://github.com/tynany/frr_exporter) on FRR/Cumulus nodes or [node_exporter](https://github.com/prometheus/node_exporter) on Linux hosts -- listening on the node's management interface.

Tell Prometheus to scrape a node by setting **grafana.port** on it:

```
nodes:
  r1:
    grafana.port: 9342          # scrape http://<mgmt-ip>:9342/metrics
  r2:
    grafana.port: 9342
```

The following per-node parameters are available:

| Parameter | Description | Default |
|-----------|-------------|---------|
| **grafana.port** | Exporter TCP port on the node. Setting it enables scraping. | *(none -- node is not scraped)* |
| **grafana.path** | Metrics HTTP path. | `/metrics` |
| **grafana.job**  | Prometheus `job` label. Nodes that share a job are grouped into one scrape job. | `netlab` |

Every scraped target gets these labels, so your dashboards can select on them:

* **instance** -- the containerlab container name (`<prefix>-<lab>-<node>`), which matches the cAdvisor `name` label, letting you correlate protocol metrics with resource metrics.
* **node** -- the netlab node name.
* **lab** -- the lab (topology) name.
* **device** -- the netlab device type.

```{tip}
netlab does **not** install exporters on the devices; it only generates the Prometheus scrape configuration. Use a device image that already runs an exporter, start one with [custom configuration templates](clab-config-template), or add it to a [custom container image](clab-linux).
```

## Adding Your Own Dashboards

Grafana automatically loads every `*.json` dashboard file in the lab's `grafana/dashboards` directory. To ship a dashboard with your lab, drop its JSON export there and restart the tool (**netlab down** / **netlab up**, or just restart the Grafana container).

The provisioned Prometheus data source has the fixed UID `prometheus`, so most community dashboards (and dashboards exported from another Grafana) work unchanged.

## Customising the Generated Configuration

The stack is generated from templates shipped with netlab. You can override any of them by placing a file with the same name in a `tools/grafana` directory inside your lab directory or your home directory (`~/.netlab/tools/grafana/`); netlab searches those locations before the built-in templates.

| File | Purpose |
|------|---------|
| `prometheus.yml` | Prometheus scrape configuration (rendered from topology). |
| `provisioning/datasources/netlab.yml` | Grafana data source definition. |
| `provisioning/dashboards/netlab.yml` | Grafana dashboard provider. |
| `dashboards/netlab-overview.json` | The default dashboard. |

The container image versions are tool parameters and can be pinned in the lab topology or user defaults:

```
tools:
  grafana:
    grafana_image: grafana/grafana:11.3.0
    prometheus_image: prom/prometheus:v3.1.0
    cadvisor_image: gcr.io/cadvisor/cadvisor:v0.49.1
```

## Topology Example

```
name: obs
provider: clab
defaults.device: frr

module: [ ospf ]

tools:
  grafana:

nodes:
  r1:
    grafana.port: 9342
    grafana.job: frr
  r2:
    grafana.port: 9342
    grafana.job: frr
  h1:
    device: linux
    module: []

links: [ r1-r2, r2-h1 ]
```

In this lab you get container-level metrics for `r1`, `r2`, and `h1` immediately, plus FRR protocol metrics from `r1` and `r2` if they run frr_exporter on port 9342.
