"""One OS lease shared by native CLI and packaged Agent entry points.

The gameplay lease uses a Windows session mutex, without depending on access to
another executable's AppData file. Other explicitly named locks retain their
file-backed implementation for launcher and installer compatibility.
"""
from pathlib import Path
import os

_leases={}
_controller_owner=None
CONTROLLER_MUTEX_NAME='Local\\MaaLimbus.Controller.v2'


def lease_path(path):
    path = Path(path)
    # A source CLI and an installed Agent have different roots. The controller
    # lock must survive app replacement and exclude both of them system-wide.
    if path.name == 'controller.lock':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))
        return (base/'MaaLimbus/controller.lock').resolve()
    return path.resolve()


class LeaseUnavailable(OSError):
    """The lease file exists but could not be opened or locked.

    Deliberately an `OSError`: a lease that cannot be taken is a refusal by the
    operating system, and every caller of the installer already treats `OSError` as
    "do not touch the files".  It was introduced as a `RuntimeError` (`2ee48ba`,
    2026-10-23 12:00) while only its *name* was being improved, which silently broke
    `tests/test_update_install.py::test_real_controller_lock_blocks_installation` --
    the guard asks for `OSError` and stopped matching, and nobody saw it because the
    suite at the time died with exit 4 before printing a summary.
    """


class ControllerLease:
    def __init__(self,path):
        self.backend='file'
        if os.name=='nt' and Path(path).name=='controller.lock':
            self._native_controller(path)
            return
        import msvcrt
        self.path=lease_path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        # A lease file that is briefly unreadable (deleted by a cleanup script while a
        # handle was still open, or held for a moment) used to surface as a raw
        # `PermissionError` traceback from the harness.  Retry once, then say what it
        # is: the caller can report a refusal instead of a Python crash.
        last=None
        for attempt in range(2):
            try:
                self.file=self.path.open('a+b')
                self.file.seek(0)
                if not self.file.read(1):
                    self.file.write(b'0');self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
                break
            except PermissionError as error:
                last=error
                try:
                    self.file.close()
                except (AttributeError,OSError):
                    pass
                if attempt:
                    raise LeaseUnavailable('the_lease_file_is_not_readable') from error
                import time as _time
                _time.sleep(.2)
            except BaseException:
                try: self.file.close()
                except (AttributeError,OSError): pass
                raise

    def _native_controller(self,path):
        import ctypes
        import threading
        from types import SimpleNamespace
        global _controller_owner
        if _controller_owner is not None and not _controller_owner.file.closed:
            raise LeaseUnavailable('another_controller_owns_game')
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
        kernel.CreateMutexW.restype=ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
        kernel.WaitForSingleObject.restype=ctypes.c_uint32
        kernel.ReleaseMutex.argtypes=[ctypes.c_void_p]
        kernel.ReleaseMutex.restype=ctypes.c_int
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        kernel.CloseHandle.restype=ctypes.c_int
        handle=kernel.CreateMutexW(None,False,CONTROLLER_MUTEX_NAME)
        if not handle:raise LeaseUnavailable('controller_mutex_unavailable: '+str(ctypes.get_last_error()))
        result=kernel.WaitForSingleObject(handle,0)
        if result not in (0,0x80):
            kernel.CloseHandle(handle)
            raise LeaseUnavailable('another_controller_owns_game' if result==258 else
                                   'controller_mutex_wait_failed: '+str(result))
        self.backend='windows_mutex'
        self.path=lease_path(path)  # Backward-compatible diagnostic identity only.
        self.file=SimpleNamespace(closed=False)
        self._kernel,self._handle=kernel,handle
        self._owner_thread=threading.get_native_id()
        self.abandoned=result==0x80
        _controller_owner=self

    @classmethod
    def acquire(cls,path):
        key=str(lease_path(path))
        lease=_leases.get(key)
        if lease is None or lease.file.closed:
            lease=cls(path);_leases[key]=lease
        elif lease.backend=='windows_mutex':
            import threading
            if lease._owner_thread!=threading.get_native_id():
                raise LeaseUnavailable('another_controller_owns_game')
        return lease

    def close(self):
        global _controller_owner
        if self.backend=='windows_mutex':
            if not self.file.closed:
                if not self._kernel.ReleaseMutex(self._handle):
                    raise LeaseUnavailable('controller_mutex_release_failed')
                self._kernel.CloseHandle(self._handle)
                self.file.closed=True
                if _controller_owner is self:_controller_owner=None
            return
        if not self.file.closed:
            import msvcrt
            self.file.seek(0)
            msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            self.file.close()
