(netlab-node)=
# Starting, Stopping, and Pausing Lab Nodes

The **netlab node** command changes the state of individual nodes in a running lab without touching the rest of the lab. It uses the transformed lab topology stored in the _netlab_ snapshot file to find the node (container) names.

```{note}
The command is implemented only for the [*containerlab*](lab-clab) provider. The **up**, **down**, and **restart** actions require *containerlab* release 0.75.0 or later.
```

## Usage

```text
$ netlab node -h
usage: netlab node [-h] [-v] [-q] [--dry-run] [-i INSTANCE]
                   node {up,down,restart,pause,unpause}

Start, stop, restart, or pause individual lab nodes (links stay intact)

positional arguments:
  node                  Node(s) to act on (node names, groups, or globs,
                        separated by commas)
  {up,down,restart,pause,unpause}
                        Action to execute on the selected nodes

options:
  -h, --help            show this help message and exit
  -v, --verbose         Verbose logging (add multiple flags for increased
                        verbosity)
  -q, --quiet           Report only major errors
  --dry-run             Print the commands that would be executed, but do not
                        execute them
  -i, --instance INSTANCE
                        Specify the lab instance to change nodes in
```

The *node* parameter is a [nodeset](netlab-inspect-node): a comma-separated list of node names, group names, or globs.

| Action | Command executed | Description |
|--------|------------------|-------------|
| **down** | `containerlab stop --node` | Stop the node container; the other nodes and their links stay up |
| **up** | `containerlab start --node` | Start a stopped node and reattach its links |
| **restart** | `containerlab restart --node` | Stop and start the node container |
| **pause** | `docker pause` | Freeze all processes in the node container |
| **unpause** | `docker unpause` | Resume a paused container |

The **[netlab status](status.md)** command displays the state reported by Docker (for example, *Up 2 minutes (Paused)* or *Exited (137) 5 seconds ago*).
