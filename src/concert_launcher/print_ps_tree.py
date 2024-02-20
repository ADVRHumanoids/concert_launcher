import psutil
import sys 
import os

def get_process_info(pid, complete=False):
    try:
        process = psutil.Process(pid)
        ppid = process.ppid()
        cmdline = process.cmdline()
        cmdline[0] = os.path.basename(cmdline[0])
        if not complete or '/tmp/concert_launcher_wrapper.bash' in cmdline or cmdline[0] == 'script':
            return ppid, cmdline, 0, 0
        cpu_usage = process.cpu_percent(.11)
        ram_usage = process.memory_info().rss / (1024 * 1024)  # Convert to MB
        return ppid, cmdline, cpu_usage, ram_usage
    except psutil.NoSuchProcess as e:
        return None

def process_tree_info(pid, level=0):

    min_level = 3

    info = get_process_info(pid, level >= min_level)
    
    if info is not None:
        ppid, cmdline, cpu_usage, ram_usage = info
        if level >= min_level:
            print(f"{' ' * ((level-min_level) * 2)}PID: {pid} ({' '.join(cmdline[:2])} ...)  CPU: {cpu_usage}  RAM: {ram_usage:.2f} MB")

        for child in psutil.Process(pid).children():
            process_tree_info(child.pid, level + 1)

# Replace 'your_pid_here' with the actual PID you want to start the tree from
starting_pid = int(sys.argv[1])
process_tree_info(starting_pid)