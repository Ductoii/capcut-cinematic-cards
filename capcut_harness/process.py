"""Bounded subprocess output and cooperative cancellation; never a shell."""
import subprocess
import tempfile
import time


def check_cancel(cancelled):
    if cancelled():
        raise InterruptedError('Job cancelled')


def run(args, *, cancelled=lambda: False, stdout=None, timeout=3600):
    check_cancel(cancelled)
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([str(x) for x in args], stdin=subprocess.DEVNULL,
                                   stdout=stdout if stdout is not None else output, stderr=errors)
        started = time.monotonic()
        try:
            while process.poll() is None:
                check_cancel(cancelled)
                if time.monotonic()-started > timeout:
                    raise TimeoutError('Media process timed out')
                time.sleep(.05)
            errors.seek(0, 2); size=errors.tell(); errors.seek(max(0, size-5000))
            message=errors.read().decode('utf-8',errors='replace')
            if process.returncode:
                raise ValueError(f'Media process failed ({process.returncode}): {message}')
            if stdout is None:
                output.seek(0, 2)
                if output.tell() > 8*1024*1024:
                    raise ValueError('Unexpectedly large media metadata response')
                output.seek(0); raw=output.read()
            else:
                raw=b''
            return raw, message
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
