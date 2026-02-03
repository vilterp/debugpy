# VSCode Python Extension Integration Guide

## Repository Information

The **Python extension for Visual Studio Code** is located at:
- **GitHub Repository**: https://github.com/microsoft/vscode-python
- **Marketplace**: https://marketplace.visualstudio.com/items?itemName=ms-python.python

## Integrating Profiling Support

The profiling feature implemented in debugpy needs to be integrated into the VSCode Python extension to provide UI controls and visualization.

### What debugpy Provides

The debugpy implementation (in this repository) provides:

1. **DAP Protocol Extensions**:
   - `startProfiling` request
   - `stopProfiling` request  
   - `profilingData` event (streamed continuously)

2. **Data Format** (with frame deduplication):
```typescript
interface ProfilingDataEvent {
  event: 'profilingData';
  body: {
    newFrames: { [frameId: string]: StackFrame };  // Only new frames
    samples: number[][];  // Arrays of frame IDs
    sampleCount: number;
    timestamp: number;
    duration: number;  // Milliseconds
  };
}

interface StackFrame {
  file: string;
  line: number;
  function: string;
}
```

### VSCode Extension Implementation Needed

To complete the profiling feature, the vscode-python extension needs:

#### 1. UI Components

**Debug Toolbar Buttons**:
- "Start Profiling" button (▶️ with flame icon)
- "Stop Profiling" button (⏹️)
- Status indicator when profiling is active

**Profiling Panel/View**:
- Flame graph visualization
- Timeline view
- Statistics panel showing:
  - Total samples collected
  - Duration of profiling session
  - Sample rate
  - Hot paths

#### 2. DAP Client Integration

```typescript
// In the debug adapter client code:

// Start profiling
await session.customRequest('startProfiling', {
    sampleInterval: 0.01  // 10ms, configurable
});

// Maintain frame map for deduplication
const frameMap = new Map<number, StackFrame>();

// Listen for profiling data events
session.onDidReceiveDebugSessionCustomEvent((event) => {
    if (event.event === 'profilingData') {
        const { newFrames, samples, duration } = event.body;
        
        // Accumulate new frames
        for (const [frameId, frame] of Object.entries(newFrames)) {
            frameMap.set(parseInt(frameId), frame);
        }
        
        // Reconstruct full stacks from frame IDs
        const fullStacks = samples.map(frameIds =>
            frameIds.map(id => frameMap.get(id))
        );
        
        // Update visualization
        updateFlameGraph(fullStacks);
    }
});

// Stop profiling
const result = await session.customRequest('stopProfiling', {});
console.log('Profiling stopped:', result.finalStats);
```

#### 3. Flame Graph Visualization

Recommended libraries:
- **d3-flame-graph**: https://github.com/spiermar/d3-flame-graph
- **speedscope**: https://github.com/jlfwong/speedscope
- Custom WebView with SVG rendering

The flame graph should:
- Show call hierarchies visually
- Support zooming and filtering
- Highlight hot paths
- Show function names, file locations, and execution percentages
- Update live as samples arrive

#### 4. Configuration Settings

Add to VSCode settings:

```json
{
  "python.profiling.sampleInterval": 0.01,
  "python.profiling.autoStart": false,
  "python.profiling.visualization": "flamegraph",
  "python.profiling.maxSamples": 10000
}
```

#### 5. Commands

Register VSCode commands:
- `python.profiling.start`
- `python.profiling.stop`
- `python.profiling.export`
- `python.profiling.clear`

### Implementation Steps for vscode-python

1. **Clone the repository**:
```bash
git clone https://github.com/microsoft/vscode-python.git
cd vscode-python
```

2. **Add profiling UI**:
   - Create new WebView panel for flame graph
   - Add toolbar buttons to debug toolbar
   - Create profiling data models

3. **Implement DAP handlers**:
   - Add event listeners for `profilingData`
   - Implement frame map accumulation
   - Handle start/stop requests

4. **Add visualization**:
   - Integrate flame graph library
   - Implement real-time updates
   - Add export functionality

5. **Testing**:
   - Unit tests for data processing
   - Integration tests with debugpy
   - UI tests for visualization

### Example File Structure in vscode-python

```
src/
  client/
    profiling/
      profilingManager.ts          # Main controller
      profilingDataHandler.ts      # DAP event handling
      frameMapManager.ts           # Frame deduplication
      views/
        flameGraphView.ts          # WebView panel
        profilingPanel.ts          # Side panel
      visualization/
        flameGraph.ts              # Flame graph rendering
        d3Integration.ts           # D3.js integration
```

### Testing the Integration

Once implemented in vscode-python, test by:

1. Install your development build of vscode-python
2. Open a Python project in VSCode
3. Start debugging a Python script
4. Click "Start Profiling" button
5. Let the code run for a few seconds
6. Click "Stop Profiling"
7. Verify flame graph appears with profiling data

### Resources

- **Debug Adapter Protocol**: https://microsoft.github.io/debug-adapter-protocol/
- **VSCode Extension API**: https://code.visualstudio.com/api
- **DAP Custom Requests**: https://microsoft.github.io/debug-adapter-protocol/specification#Requests_Custom
- **debugpy Documentation**: https://github.com/microsoft/debugpy/wiki

### Getting Help

For questions about:
- **debugpy (this repo)**: Open an issue at https://github.com/microsoft/debugpy/issues
- **vscode-python**: Open an issue at https://github.com/microsoft/vscode-python/issues
- **DAP specification**: Check https://microsoft.github.io/debug-adapter-protocol/

---

## Quick Reference: What's Implemented

In **debugpy** (this repository) ✅:
- [x] Server-side profiling using `sys.setprofile()`
- [x] Frame deduplication (75-90% data reduction)
- [x] DAP protocol extensions (requests + events)
- [x] Sample batching and streaming
- [x] Duration tracking
- [x] Dataclass models (StackFrame, SampleBatch, ProfilingResult)

In **vscode-python** (needs implementation) ❌:
- [ ] UI controls (start/stop buttons)
- [ ] DAP client handlers
- [ ] Frame map accumulation
- [ ] Flame graph visualization
- [ ] Export functionality
- [ ] Settings/configuration
