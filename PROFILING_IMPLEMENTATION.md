# Profiling Support Implementation Summary

This PR adds profiling support to debugpy, enabling live profiling of Python applications during debug sessions with flame graph visualization.

## What's Implemented

### 1. Server-Side Profiling Module (`src/debugpy/server/profiling.py`)
- Uses Python's `sys.setprofile()` API for accurate call stack capture
- Time-based sampling (default: 10ms intervals = 100 samples/second)
- Batched sample streaming to reduce overhead
- Automatic filtering of debugpy/pydevd internal frames
- Thread-safe implementation with proper locking

### 2. DAP Protocol Extensions

#### New Requests:
- **`startProfiling`**: Start profiling with configurable sample interval
  ```json
  {
    "command": "startProfiling",
    "arguments": {
      "sampleInterval": 0.01  // seconds (optional, default 0.01)
    }
  }
  ```

- **`stopProfiling`**: Stop profiling and get final statistics
  ```json
  {
    "command": "stopProfiling",
    "arguments": {}
  }
  ```

#### New Event:
- **`profilingData`**: Streamed periodically with profiling samples
  ```json
  {
    "event": "profilingData",
    "body": {
      "samples": [
        [
          {"file": "/app/main.py", "line": 10, "function": "main"},
          {"file": "/app/utils.py", "line": 42, "function": "calculate"}
        ]
      ],
      "sampleCount": 10,
      "timestamp": 1234567890.123
    }
  }
  ```

### 3. Protocol Schema Definitions
Added to `pydevd_schema.py`:
- `PydevdStartProfilingRequest` / `PydevdStartProfilingArguments` / `PydevdStartProfilingResponse`
- `PydevdStopProfilingRequest` / `PydevdStopProfilingArguments` / `PydevdStopProfilingResponse`  
- `PydevdProfilingDataEvent` / `PydevdProfilingDataEventBody`

### 4. Request Handlers
- **Server side** (`pydevd_process_net_command_json.py`):
  - `on_pydevdstartprofiling_request()` - starts profiler with callback
  - `on_pydevdstopprofiling_request()` - stops profiler and returns stats

- **Adapter side** (`clients.py`):
  - `startProfiling_request()` - forwards to server
  - `stopProfiling_request()` - forwards to server

- **Event forwarding** (`servers.py`):
  - `pydevdprofilingdata_event()` - converts and forwards samples to client

### 5. Documentation
- **`doc/PROFILING.md`**: Comprehensive documentation
  - Architecture overview
  - API reference
  - Usage examples
  - Technical notes on implementation
  - Future enhancement ideas

- **`examples/profiling_example.py`**: Working example script

### 6. Tests
- **`tests/debugpy/test_profiling.py`**:
  - `test_start_stop_profiling`: Basic lifecycle test
  - `test_profiling_data_format`: Validates sample structure
  - `test_stop_profiling_without_start`: Error handling

## Key Design Decisions

### Why sys.setprofile() instead of sys._current_frames()?
1. **Official Python API**: `setprofile()` is the standard profiling mechanism
2. **Accurate call stacks**: Provides correct frame information during execution
3. **Aligned with Python's profiling model**: Works like cProfile/profile
4. **Event-driven**: Can capture stacks at function calls/returns with proper context

### Sample Format: Individual Stacks
Each sample is a complete call stack (array of frames), not aggregated statistics:
- **Perfect for flame graphs**: Can visualize call hierarchies
- **Time-series data**: Can see how execution evolves over time
- **Flexible analysis**: Client can aggregate/filter as needed

### Performance Considerations
- **Low overhead**: Time-based sampling (not every function call)
- **Batching**: 10 samples per event reduces message traffic
- **Filtered frames**: Internal debugpy frames excluded
- **Daemon threads**: Don't block application exit

## Files Changed

### New Files:
- `src/debugpy/server/profiling.py` - Core profiling implementation
- `tests/debugpy/test_profiling.py` - Test suite
- `doc/PROFILING.md` - Documentation
- `examples/profiling_example.py` - Usage example

### Modified Files:
- `src/debugpy/_vendored/pydevd/_pydevd_bundle/_debug_adapter/pydevd_schema.py` - Protocol schemas
- `src/debugpy/_vendored/pydevd/_pydevd_bundle/pydevd_process_net_command_json.py` - Request handlers
- `src/debugpy/adapter/clients.py` - Client-side request handlers
- `src/debugpy/adapter/servers.py` - Event forwarding

## Testing

Run tests:
```bash
python3 -m pytest tests/debugpy/test_profiling.py -xvs
```

Manual testing:
```python
from debugpy.server import profiling

def callback(data):
    print(f'Received {data["sampleCount"]} samples')

profiling.start_profiling(0.01, callback)
# ... do some work ...
profiling.stop_profiling()
```

## Next Steps (VSCode Extension)

To enable this feature in VSCode:

1. **Add UI Controls**:
   - "Start Profiling" / "Stop Profiling" buttons in debug toolbar
   - Status indicator when profiling is active

2. **Send DAP Requests**:
   ```typescript
   // Start profiling
   await session.customRequest('startProfiling', {
       sampleInterval: 0.01
   });
   
   // Stop profiling
   await session.customRequest('stopProfiling', {});
   ```

3. **Handle Events**:
   ```typescript
   session.onDidReceiveDebugSessionCustomEvent((event) => {
       if (event.event === 'profilingData') {
           updateFlameGraph(event.body.samples);
       }
   });
   ```

4. **Render Flame Graph**:
   - Use samples to build/update live flame graph
   - Popular libraries: d3-flame-graph, speedscope
   - Each sample is a stack (array of frames)

## Benefits

1. **Live profiling**: Profile applications during debug sessions without restart
2. **Button-click simplicity**: No code changes needed
3. **Visual feedback**: Real-time flame graphs show performance bottlenecks
4. **Integrated workflow**: Profiling built into debug experience
5. **Flexible**: Configurable sample rates, filtered frames

## Compatibility

- ✅ Python 3.7+
- ✅ All platforms (Windows, Linux, macOS)
- ✅ Works with existing debugpy features
- ✅ No breaking changes to existing APIs
- ✅ Backward compatible (profiling is opt-in)
