# Profiling Support for debugpy

This document describes the profiling support added to debugpy, which enables live profiling of Python applications during debug sessions.

## Overview

The profiling feature allows developers to:
1. Start profiling a running Python process from VSCode during a debug session
2. Receive live stack trace samples streamed over the Debug Adapter Protocol (DAP)
3. Render the samples in a flame graph or other visualizations in VSCode

## Implementation Details

### Architecture

The profiling implementation consists of three main components:

1. **Server-side profiler** (`src/debugpy/server/profiling.py`):
   - Uses Python's `sys.setprofile()` to capture call stacks
   - Samples stacks at regular intervals (default 10ms)
   - Batches samples and streams them to the adapter

2. **DAP Protocol Extensions**:
   - `startProfiling` request: Start profiling with configurable sample interval
   - `stopProfiling` request: Stop profiling and get final statistics
   - `profilingData` event: Streams profiling samples to the client

3. **Adapter handlers** (`src/debugpy/adapter/clients.py` and `servers.py`):
   - Forward profiling requests from IDE to server
   - Forward profiling data events from server to IDE

### Sample Format

Each profiling sample is a **call stack** represented as an array of stack frames, ordered from caller to callee (root to leaf). This format is ideal for flame graph visualization.

Example sample:
```json
{
  "samples": [
    [
      {"file": "/app/main.py", "line": 10, "function": "main"},
      {"file": "/app/main.py", "line": 25, "function": "process_data"},
      {"file": "/app/utils.py", "line": 42, "function": "calculate"}
    ],
    [
      {"file": "/app/main.py", "line": 10, "function": "main"},
      {"file": "/app/main.py", "line": 30, "function": "save_results"}
    ]
  ],
  "sampleCount": 2,
  "timestamp": 1234567890.123
}
```

## Usage

### From VSCode Extension

The VSCode Python extension can add a "Start Profiling" button that sends the `startProfiling` request:

```typescript
// Start profiling with 10ms sample interval
const response = await session.customRequest('startProfiling', {
    sampleInterval: 0.01
});

// Listen for profiling data events
session.onDidReceiveDebugSessionCustomEvent((event) => {
    if (event.event === 'profilingData') {
        const { samples, sampleCount, timestamp } = event.body;
        // Update flame graph visualization
        updateFlameGraph(samples);
    }
});

// Stop profiling
const stopResponse = await session.customRequest('stopProfiling', {});
```

### Programmatically (for testing)

```python
import debugpy
import time

# Start debugpy
debugpy.listen(5678)
debugpy.wait_for_client()

# Your application code here
def my_function():
    time.sleep(0.1)

my_function()

# Profiling is controlled by the IDE via DAP requests
# The application code doesn't need to do anything special
```

## Technical Notes

### Using sys.setprofile()

The profiler uses `sys.setprofile()` rather than `sys._current_frames()` because:

1. **Accurate call stacks**: `setprofile()` is Python's official profiling API and provides accurate frame information during execution
2. **Aligned with Python profiling model**: Works consistently with cProfile and other profiling tools
3. **Event-driven sampling**: Can capture stacks at function calls/returns, providing better context

The profiler implements time-based sampling within the profile callback to avoid capturing every single function call (which would be too expensive).

### Performance Considerations

- Default sample interval: 10ms (100 samples/second)
- Samples are batched (10 samples per event) to reduce DAP message overhead
- Internal debugpy/pydevd frames are filtered out to reduce noise
- Uses daemon threads to avoid blocking the main application

### Frame Filtering

The profiler automatically filters out internal debugpy and pydevd frames to focus on user code. This can be disabled if needed by modifying the `_should_skip_frame()` method.

## Future Enhancements

Potential improvements for future versions:

1. **Multi-threaded profiling**: Currently focuses on main thread; could be extended to profile all threads
2. **CPU vs Wall-clock time**: Add options for different timing modes
3. **Memory profiling**: Extend to capture memory allocations
4. **Custom sampling strategies**: Allow plugins to define custom sampling logic
5. **Profile persistence**: Save/load profiling sessions for later analysis

## API Reference

### Request: `startProfiling`

Start profiling the debugged process.

**Arguments**:
- `sampleInterval` (number, optional): Sample interval in seconds (default: 0.01)

**Response**:
```json
{
    "status": "started" | "already_running" | "error"
}
```

### Request: `stopProfiling`

Stop profiling the debugged process.

**Arguments**: None

**Response**:
```json
{
    "status": "stopped" | "not_running" | "error",
    "finalStats": {
        "totalSamples": 100
    }
}
```

### Event: `profilingData`

Sent periodically while profiling is active. Contains a batch of stack trace samples.

**Body**:
```json
{
    "samples": [
        [
            {"file": "...", "line": 10, "function": "main"},
            {"file": "...", "line": 20, "function": "helper"}
        ]
    ],
    "sampleCount": 10,
    "timestamp": 1234567890.123
}
```

## Testing

Run the profiling tests:

```bash
python3 -m pytest tests/debugpy/test_profiling.py -xvs
```

The test suite includes:
- Basic start/stop profiling lifecycle
- Profiling data format validation  
- Error handling (stop without start)
