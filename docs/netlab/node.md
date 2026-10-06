(netlab-node)=
# Starting, Stopping, and Pausing Lab Nodes

The **netlab node** command changes the state of individual nodes in a running lab without touching the rest of the lab. It uses the transformed lab topology stored in the _netlab_ snapshot file to find the node (container) names.

```{note}
The command is currently implemented only for the [*containerlab*](lab-clab) provider. *Containerlab* **start**, **stop** and **restart** actions require *containerlab* release 0.75.0 or later.
```

## Usage

```text
$ netlab node -h
usage: netlab node [-h] [-v] [-q] [--dry-run] [-i INSTANCE]
                   node {start,stop,restart,pause,unpause}

Start, stop, restart, or pause individual lab nodes (links stay intact)

positional arguments:
  node                  Node(s) to act on (node names, groups, or globs, separated by commas)
  {start,stop,restart,pause,unpause}
                        Action to execute on the selected nodes

options:
  -h, --help            show this help message and exit
  -v, --verbose         Verbose logging (add multiple flags for increased verbosity)
  -q, --quiet           Report only major errors
  --dry-run             Print the commands that would be executed, but do not execute them
  -i INSTANCE, --instance INSTANCE
                        Specify lab instance to change nodes in

Aliases: up = start, down = stop, resume = unpause
```

The *node* parameter is a [nodeset](netlab-inspect-node): a comma-separated list of node names, group names, or globs.

## Actions

| Action | Implementation | Description |
|--------|----------------|-------------|
| **stop** (**down**) | `containerlab stop --node` | Stop the node container; the other nodes and the links they use stay up |
| **start** (**up**) | `containerlab start --node` | Start a stopped node and reattach its links |
| **restart** | `containerlab restart --node` | Stop and start a node |
| **pause** | `docker pause` | Freeze all processes in the node container |
| **unpause** (**resume**) | `docker unpause` | Resume a paused container |

```{warning}
Starting or restarting a node does not reapply the configuration created by **netlab initial**. Containers that keep their configuration only in memory boot with the configuration specified in the *containerlab* startup files; use **[netlab initial](initial.md) --limit *node*** to deploy the initial configuration again.
```

## Examples

Restart *r2* and pause *r1* and *r3*:

```
$ netlab node r2 restart
$ netlab node r1,r3 pause
$ netlab node r1,r3 unpause
```
