import subprocess
from ctypes import (WinError, byref, c_int, c_long, c_ulong,
                    create_string_buffer, windll)


class DLLInjector:
    ACCESS_MASK = (0x000F0000 | 0x00100000 | 0x00000FFF)
    MEM_FLAGS = 0x00001000 | 0x00002000
    FREE_MEM = 0x8000
    RWX_PERMISSIONS = 0x40

    def __init__(self):
        self.k32 = windll.kernel32
        self.u32 = windll.user32
        self.process_id = c_ulong()
        self.proc_handle = None

    def launch_target(self, exe_path):
        return subprocess.Popen([exe_path]).pid

    def attach_to_pid(self, pid):
        self.cleanup()
        self.process_id = c_ulong(pid)
        self.proc_handle = self.k32.OpenProcess(self.ACCESS_MASK, 0, pid, stdin=subprocess.DEVNULL)
        if not self.proc_handle:
            raise WinError()

    def cleanup(self):
        if self.proc_handle:
            self.k32.CloseHandle(self.proc_handle)
            if not self.proc_handle:
                raise WinError()
        self.proc_handle = None

    def allocate_remote_buffer(self, data, length):
        address = self.k32.VirtualAllocEx(self.proc_handle, None, c_int(length),
                                          self.MEM_FLAGS, self.RWX_PERMISSIONS)
        if not address:
            raise WinError()
        self.write_to_memory(address, data)
        return address

    def release_remote_buffer(self, addr, length):
        if not self.k32.VirtualFreeEx(self.proc_handle, addr, c_int(0), self.FREE_MEM):
            raise WinError()

    def get_func_address(self, dll, func):
        module_base = self.k32.GetModuleHandleA(dll.encode("ascii"))
        if not module_base:
            raise WinError()
        func_ptr = self.k32.GetProcAddress(module_base, func.encode("ascii"))
        if not func_ptr:
            raise WinError()
        return func_ptr

    def run_remote_function(self, addr, arg_data):
        exit_code = c_long(0)
        arg_ptr = self.allocate_remote_buffer(arg_data, len(arg_data))
        thread = self.k32.CreateRemoteThread(self.proc_handle, None, None, c_long(addr),
                                             c_long(arg_ptr), None, None)
        if not thread:
            raise WinError()
        if self.k32.WaitForSingleObject(thread, 0xFFFFFFFF) == 0xFFFFFFFF:
            raise WinError()
        if not self.k32.GetExitCodeThread(thread, byref(exit_code)):
            raise WinError()
        self.release_remote_buffer(arg_ptr, len(arg_data))
        return exit_code.value

    def read_memory_region(self, address, length):
        buf = create_string_buffer(length)
        if not self.k32.ReadProcessMemory(self.proc_handle, c_long(address), buf, length, None):
            raise WinError()
        return buf

    def write_to_memory(self, address, payload):
        if not self.k32.WriteProcessMemory(self.proc_handle, address, payload, len(payload), None):
            raise WinError()

    def load_library_into_target(self, dll_bytes):
        func_ptr = self.get_func_address("kernel32.dll", "LoadLibraryA")
        result = self.run_remote_function(func_ptr, dll_bytes)
        return result

    def inject_shared_library(self, dll_path):
        return self.load_library_into_target(dll_path.encode("ascii"))

    def execute_exported(self, dll_path, base_addr, func_name, raw_args):
        offset = self.resolve_func_offset(dll_path.encode("ascii"), func_name)
        self.run_remote_function(base_addr + offset, raw_args)

    def resolve_func_offset(self, module_path, func_name):
        temp_base = self.k32.LoadLibraryA(module_path)
        if not temp_base:
            raise WinError()
        func_ptr = self.k32.GetProcAddress(temp_base, func_name.encode("ascii"))
        if not func_ptr:
            raise WinError()
        if not self.k32.FreeLibrary(temp_base):
            raise WinError()
        return func_ptr - temp_base
