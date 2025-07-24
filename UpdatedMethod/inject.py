import psutil
from injector import DLLInjector
import time
import os

agent = DLLInjector()

dll_file = os.path.join(os.getcwd(), "DLLHooks.dll")
if not os.path.exists(dll_file):
    dll_file = os.path.join(os.getcwd(), "DLLHooks/Release/DLLHooks.dll")
    if not os.path.exists(dll_file):
        raise FileNotFoundError("DLLHooks.dll not found in expected directories.")

monitored_process = "LockDownBrowser"

for task in psutil.process_iter(['name']):
    task_name = task.name()
    if monitored_process in task_name:
        try:
            print(f"Terminating: {task_name} (PID: {task.pid})")
            task.kill()
        except Exception as err:
            print("Could not terminate:", err)

print("Monitoring for target process...")

while True:
    found = False
    for task in psutil.process_iter(['name']):
        task_name = task.name()
        if monitored_process in task_name:
            pid = task.pid
            print(f"Target detected: {task_name} (PID: {pid})")
            try:
                agent.attach_to_pid(pid)
                agent.inject_shared_library(dll_file)
                agent.cleanup()
                found = True
                break
            except Exception as err:
                print("Injection error:", err)
    if found:
        break

print("Operation completed.")
