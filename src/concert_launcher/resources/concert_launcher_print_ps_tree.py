import psutil
import sys 
import os
import time

process_dict = {}

def get_process_info(pid):
    
    if pid not in process_dict.keys():
        process_dict[pid] = psutil.Process(pid)
    
    process = process_dict[pid]
    
    try:
        ppid = process.ppid()
        cmdline = process.cmdline()
        cmdline[0] = os.path.basename(cmdline[0])
        cpu_usage = process.cpu_percent()
        ram_usage = process.memory_info().rss / (1024 * 1024)  # Convert to MB
        return ppid, cmdline, cpu_usage, ram_usage
    except psutil.NoSuchProcess as e:
        return None

def process_tree_info(pid, level=0, print_to_screen=False):

    min_level = 2

    info = get_process_info(pid)
    
    if info is not None:
        
        ppid, cmdline, cpu_usage, ram_usage = info
        
        if print_to_screen and level >= min_level:
            print(f"{' ' * ((level-min_level) * 2)}PID: {pid} ({' '.join(cmdline[:2])} ...)  CPU: {cpu_usage}  RAM: {ram_usage:.2f} MB")

        for child in psutil.Process(pid).children():
            process_tree_info(child.pid, level + 1, print_to_screen=print_to_screen)

# Replace 'your_pid_here' with the actual PID you want to start the tree from
starting_pid = int(sys.argv[1])
process_tree_info(starting_pid)
time.sleep(0.2)
process_tree_info(starting_pid, print_to_screen=True)