# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""
Profiling support for debugpy.

This module provides profiling capabilities that can be started/stopped
during a debug session and streams profiling samples back to the client.

Uses Python's sys.setprofile() to capture accurate call stacks at regular intervals.
Each sample is a stack trace (array of stack frames) captured at a point in time.
"""

import sys
import threading
import time
from typing import Optional, Callable, Dict, Any, List

from debugpy.common import log


class Profiler:
    """Manages sampling profiling for the debugged process using sys.setprofile()."""

    def __init__(self, on_data_callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """
        Initialize the profiler.
        
        Args:
            on_data_callback: Optional callback to invoke with profiling data.
                             Called with a dictionary containing stack trace samples.
        """
        self._is_profiling = False
        self._lock = threading.RLock()
        self._on_data_callback = on_data_callback
        self._sample_thread: Optional[threading.Thread] = None
        self._should_stop = threading.Event()
        self._sample_interval = 0.01  # Sample every 10ms by default for live updates
        self._samples_buffer: List[List[Dict[str, Any]]] = []
        self._batch_size = 10  # Send samples in batches
        self._last_sample_time = 0
        self._current_frame = None  # Track the current frame for profiling
        
    def start(self, sample_interval: float = 0.01) -> Dict[str, Any]:
        """
        Start profiling using sys.setprofile().
        
        Args:
            sample_interval: How often to capture stack samples (in seconds, default 0.01 = 10ms)
            
        Returns:
            Dictionary with status information
        """
        with self._lock:
            if self._is_profiling:
                log.warning("Profiler is already running")
                return {"status": "already_running"}
            
            log.info("Starting profiler with sample interval: {0}s", sample_interval)
            self._sample_interval = sample_interval
            self._is_profiling = True
            self._should_stop.clear()
            self._samples_buffer = []
            self._last_sample_time = time.time()
            
            # Install the profile function on the main thread
            # This will be called on every function call/return/exception
            sys.setprofile(self._profile_func)
            
            # Start background thread to periodically send batched samples
            self._sample_thread = threading.Thread(
                target=self._send_loop,
                name="debugpy-profiler-sender",
                daemon=True
            )
            self._sample_thread.start()
            
            return {"status": "started"}
    
    def stop(self) -> Dict[str, Any]:
        """
        Stop profiling and return summary.
        
        Returns:
            Dictionary with profiling summary
        """
        with self._lock:
            if not self._is_profiling:
                log.warning("Profiler is not running")
                return {"status": "not_running"}
            
            log.info("Stopping profiler")
            self._should_stop.set()
            self._is_profiling = False
            
            # Uninstall the profile function
            sys.setprofile(None)
            
            # Wait for send thread to finish
            if self._sample_thread and self._sample_thread.is_alive():
                self._sample_thread.join(timeout=2.0)
            
            # Send any remaining buffered samples
            if self._samples_buffer and self._on_data_callback:
                try:
                    self._send_samples(self._samples_buffer)
                except Exception as e:
                    log.exception("Error sending final samples: {0}", e)
            
            sample_count = len(self._samples_buffer)
            
            # Clean up
            self._sample_thread = None
            self._samples_buffer = []
            
            return {
                "status": "stopped",
                "finalStats": {
                    "totalSamples": sample_count
                }
            }
    
    def is_profiling(self) -> bool:
        """Check if profiling is currently active."""
        with self._lock:
            return self._is_profiling
    
    def _profile_func(self, frame, event, arg):
        """
        Profile function called by sys.setprofile() on function calls/returns.
        
        Args:
            frame: The current frame being executed
            event: 'call', 'return', 'c_call', 'c_return', 'c_exception', or 'exception'
            arg: Depends on event type
        """
        if not self._is_profiling:
            return
        
        # Sample at regular intervals based on time
        current_time = time.time()
        if current_time - self._last_sample_time >= self._sample_interval:
            self._last_sample_time = current_time
            
            try:
                # Capture the call stack from this frame
                stack = self._capture_stack_from_frame(frame)
                
                if stack:
                    with self._lock:
                        self._samples_buffer.append(stack)
                        
            except Exception as e:
                log.exception("Error capturing stack sample: {0}", e)
    
    def _send_loop(self):
        """Background thread that periodically sends batched samples."""
        while not self._should_stop.wait(self._sample_interval * self._batch_size):
            try:
                with self._lock:
                    if len(self._samples_buffer) >= self._batch_size:
                        samples_to_send = self._samples_buffer[:self._batch_size]
                        self._samples_buffer = self._samples_buffer[self._batch_size:]
                        
                        if self._on_data_callback:
                            self._send_samples(samples_to_send)
                            
            except Exception as e:
                log.exception("Error in send loop: {0}", e)
    
    def _capture_stack_from_frame(self, frame) -> Optional[List[Dict[str, Any]]]:
        """
        Capture the call stack from a frame object.
        
        Args:
            frame: The frame to start from
            
        Returns:
            List of stack frames (top to bottom - caller to callee), or None if capture failed.
            Each frame is a dict with: file, line, function
        """
        try:
            stack = []
            current_frame = frame
            
            # Walk up the stack (from current to caller)
            while current_frame is not None:
                code = current_frame.f_code
                filename = code.co_filename
                line = current_frame.f_lineno
                func_name = code.co_name
                
                # Skip debugpy internal frames to reduce noise
                if not self._should_skip_frame(filename):
                    stack.append({
                        "file": filename,
                        "line": line,
                        "function": func_name,
                    })
                
                current_frame = current_frame.f_back
            
            # Reverse to get caller-to-callee order (root to leaf)
            stack.reverse()
            
            return stack if stack else None
            
        except Exception as e:
            log.exception("Error capturing stack from frame: {0}", e)
            return None
    
    def _should_skip_frame(self, filename: str) -> bool:
        """
        Check if a frame should be skipped from profiling samples.
        
        Args:
            filename: The filename of the frame
            
        Returns:
            True if frame should be skipped
        """
        # Skip debugpy and pydevd internal frames
        skip_patterns = [
            '/debugpy/',
            '\\debugpy\\',
            '/pydevd',
            '\\pydevd',
            '<frozen',
        ]
        
        for pattern in skip_patterns:
            if pattern in filename:
                return True
        
        return False
    
    def _send_samples(self, samples: List[List[Dict[str, Any]]]):
        """
        Send a batch of samples to the callback.
        
        Args:
            samples: List of stack traces to send
        """
        if not self._on_data_callback or not samples:
            return
        
        try:
            data = {
                "samples": samples,
                "sampleCount": len(samples),
                "timestamp": time.time()
            }
            self._on_data_callback(data)
        except Exception as e:
            log.exception("Error sending samples: {0}", e)


# Global profiler instance
_profiler: Optional[Profiler] = None
_profiler_lock = threading.RLock()


def get_profiler(on_data_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Profiler:
    """
    Get or create the global profiler instance.
    
    Args:
        on_data_callback: Optional callback to invoke with profiling data
        
    Returns:
        The global Profiler instance
    """
    global _profiler
    with _profiler_lock:
        if _profiler is None:
            _profiler = Profiler(on_data_callback)
        elif on_data_callback and _profiler._on_data_callback != on_data_callback:
            # Update callback if provided
            _profiler._on_data_callback = on_data_callback
        return _profiler


def start_profiling(sample_interval: float = 0.01,
                    on_data_callback: Optional[Callable[[Dict[str, Any]], None]] = None
                    ) -> Dict[str, Any]:
    """
    Start profiling the current process using sys.setprofile().
    
    Args:
        sample_interval: How often to capture stack samples (in seconds, default 0.01 = 10ms)
        on_data_callback: Optional callback to invoke with profiling data
        
    Returns:
        Dictionary with status information
    """
    profiler = get_profiler(on_data_callback)
    return profiler.start(sample_interval)


def stop_profiling() -> Dict[str, Any]:
    """
    Stop profiling the current process.
    
    Returns:
        Dictionary with final profiling statistics
    """
    profiler = get_profiler()
    return profiler.stop()


def is_profiling() -> bool:
    """Check if profiling is currently active."""
    with _profiler_lock:
        if _profiler is None:
            return False
        return _profiler.is_profiling()
