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

Profiling data is sent as events with **frame deduplication** for efficiency. Each profiling event contains:

1. **`newFrames`**: A dictionary mapping frame IDs to frame data. Only frames that haven't been sent before are included.
2. **`samples`**: An array of call stacks, where each stack is an array of frame IDs (integers).
3. **`duration`**: Duration of the sampling window in milliseconds (time from start of batch to send).

This design minimizes data transfer by only sending each unique frame once per profiling session.

Example event:
```json
{
  "newFrames": {
    "12345": {"file": "/app/main.py", "line": 10, "function": "main"},
    "67890": {"file": "/app/utils.py", "line": 42, "function": "calculate"}
  },
  "samples": [
    [12345, 67890],
    [12345, 67890],
    [12345, 99999]
  ],
  "sampleCount": 3,
  "timestamp": 1234567890.123,
  "duration": 150.5
}
```

In subsequent events, if the same frames appear, only the frame IDs are sent:
```json
{
  "newFrames": {
    "11111": {"file": "/app/other.py", "line": 5, "function": "helper"}
  },
  "samples": [
    [12345, 11111],
    [12345, 67890]
  ],
  "sampleCount": 2,
  "timestamp": 1234567890.456,
  "duration": 100.2
}
```

The client maintains a frame ID → frame mapping to reconstruct full stacks.

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
        const { newFrames, samples, sampleCount, timestamp } = event.body;
        
        // Update frame mapping
        for (const [frameId, frameData] of Object.entries(newFrames)) {
            frameMap.set(parseInt(frameId), frameData);
        }
        
        // Reconstruct full stacks from frame IDs
        const fullStacks = samples.map(frameIds => 
            frameIds.map(id => frameMap.get(id))
        );
        
        // Update flame graph visualization
        updateFlameGraph(fullStacks);
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

### Frame Deduplication

The profiler uses frame deduplication to minimize data transfer:

1. **Frame ID Generation**: Each unique stack frame (file, line, function) is assigned a stable integer ID using a hash function
2. **State Tracking**: The profiler maintains:
   - `frame_id_map`: Maps frame IDs to StackFrame dataclasses
   - `sent_frame_ids`: Set of frame IDs already sent to the client
3. **Efficient Transmission**: Only new frames are sent in each event's `newFrames` field
4. **Client Reconstruction**: The client accumulates a frame ID → frame data map and uses it to reconstruct full call stacks

This typically reduces data size by 75-90% after the first batch, as the same frames appear repeatedly in different samples.

### Using Dataclasses

The implementation uses Python dataclasses for type safety:

- `StackFrame`: Represents a single stack frame with file, line, and function
- `ProfilingResult`: Result of start/stop operations
- `ProfilingData`: Complete profiling data sent to callbacks

This provides better IDE support, type checking, and cleaner code compared to dictionaries.

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

Sent periodically while profiling is active. Contains new stack frames and samples as frame ID arrays.

**Body**:
```json
{
    "newFrames": {
        "12345": {"file": "...", "line": 10, "function": "main"},
        "67890": {"file": "...", "line": 20, "function": "helper"}
    },
    "samples": [
        [12345, 67890],
        [12345]
    ],
    "sampleCount": 2,
    "timestamp": 1234567890.123,
    "duration": 150.5
}
```

**Fields**:
- `newFrames`: Dictionary mapping frame IDs (as strings) to frame objects. Only includes frames not previously sent.
- `samples`: Array of call stacks. Each stack is an array of frame IDs (integers).
- `sampleCount`: Number of samples in this batch.
- `timestamp`: Unix timestamp when samples were collected.
- `duration`: Duration of the sampling window in milliseconds (time from batch start to send).

## Testing

Run the profiling tests:

```bash
python3 -m pytest tests/debugpy/test_profiling.py -xvs
```

The test suite includes:
- Basic start/stop profiling lifecycle
- Profiling data format validation  
- Error handling (stop without start)
