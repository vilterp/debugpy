# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

"""
Profiling support for debugpy.

This module provides profiling capabilities that can be started/stopped
during a debug session and streams profiling samples back to the client.

Each sample is a stack trace (array of stack frames) captured at a point in time.
"""

import sys
import threading
import time
import traceback
from typing import Optional, Callable, Dict, Any, List

from debugpy.common import log


class Profiler:
    """Manages sampling profiling for the debugged process."""

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
        self._main_thread_id = threading.main_thread().ident
        self._samples_buffer: List[List[Dict[str, Any]]] = []
        self._batch_size = 10  # Send samples in batches
        
    def start(self, sample_interval: float = 0.01) -> Dict[str, Any]:
        """
        Start profiling.
        
        Args:
            sample_interval: How often to sample stack traces (in seconds, default 0.01 = 10ms)
            
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
            
            # Start background thread to periodically collect and send samples
            self._sample_thread = threading.Thread(
                target=self._sample_loop,
                name="debugpy-profiler-sampler",
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
            
            # Wait for sample thread to finish
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
    
    def _sample_loop(self):
        """Background thread that periodically samples stack traces from all threads."""
        while not self._should_stop.wait(self._sample_interval):
            try:
                # Capture stack traces from all threads
                stack_sample = self._capture_stack_sample()
                
                if stack_sample:
                    with self._lock:
                        self._samples_buffer.append(stack_sample)
                        
                        # Send samples in batches to avoid too many events
                        if len(self._samples_buffer) >= self._batch_size:
                            if self._on_data_callback:
                                self._send_samples(self._samples_buffer)
                            self._samples_buffer = []
                            
            except Exception as e:
                log.exception("Error sampling stack trace: {0}", e)
    
    def _capture_stack_sample(self) -> Optional[List[Dict[str, Any]]]:
        """
        Capture the current stack trace from the main thread.
        
        Returns:
            List of stack frames (bottom to top), or None if capture failed.
            Each frame is a dict with: file, line, function, code
        """
        try:
            # Get all thread frames
            all_frames = sys._current_frames()
            
            # Focus on main thread for now (can be extended to all threads)
            if self._main_thread_id not in all_frames:
                return None
            
            frame = all_frames[self._main_thread_id]
            
            # Build stack trace from bottom (oldest) to top (newest)
            stack = []
            while frame is not None:
                # Extract frame information
                code = frame.f_code
                filename = code.co_filename
                line = frame.f_lineno
                func_name = code.co_name
                
                # Skip debugpy internal frames to reduce noise
                if not self._should_skip_frame(filename):
                    stack.append({
                        "file": filename,
                        "line": line,
                        "function": func_name,
                    })
                
                frame = frame.f_back
            
            # Reverse to get top-to-bottom order (caller to callee)
            stack.reverse()
            
            return stack if stack else None
            
        except Exception as e:
            log.exception("Error capturing stack sample: {0}", e)
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
                   on_data_callback: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    """
    Start profiling the current process.
    
    Args:
        sample_interval: How often to sample stack traces (in seconds, default 0.01 = 10ms)
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
    global _profiler
    with _profiler_lock:
        if _profiler is None:
            return False
        return _profiler.is_profiling()
