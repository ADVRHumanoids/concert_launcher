import os
import sys

import psutil


def process_label(process):
    try:
        cmdline = process.cmdline()
        name = os.path.basename(cmdline[0]) if cmdline else process.name()
        detail = " ".join(cmdline[1:3])
        memory = process.memory_info().rss / (1024 * 1024)
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return None

    suffix = " {} ...".format(detail) if detail else ""
    return "PID: {} ({}{}) RAM: {:.2f} MB".format(
        process.pid,
        name,
        suffix,
        memory,
    )


def print_tree(process, level=0):
    label = process_label(process)
    if label is None:
        return
    print("{}{}".format("  " * level, label))

    try:
        children = process.children()
    except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
        return

    for child in children:
        print_tree(child, level + 1)


if __name__ == "__main__":
    root = psutil.Process(int(sys.argv[1]))
    print_tree(root)
