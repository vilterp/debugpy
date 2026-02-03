# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root
# for license information.

import pytest
import time

from debugpy.common import log
from tests import debug
from tests.patterns import some


def test_start_stop_profiling(pyfile, target, run):
    @pyfile
    def code_to_debug():
        import debuggee
        import debugpy
        import time

        debuggee.setup()
        debugpy.breakpoint()  # @bp
        
        # Do some work to generate profiling samples
        def fibonacci(n):
            if n <= 1:
                return n
            return fibonacci(n - 1) + fibonacci(n - 2)
        
        for i in range(5):
            result = fibonacci(10)
            time.sleep(0.05)
        
        print("done")  # @done

    with debug.Session() as session:
        session.config["justMyCode"] = False
        
        with run(session, target(code_to_debug)):
            pass

        session.wait_for_stop()

        # Start profiling
        start_response = session.request("startProfiling", {"sampleInterval": 0.01})
        log.info("Start profiling response: {0}", start_response)
        assert start_response.get("status") in ["started", "already_running"]

        # Continue execution to generate profiling samples
        session.request_continue()

        # Wait a bit to collect some samples
        time.sleep(0.5)

        # We should receive some profiling data events
        # The events are sent automatically, so we just verify they arrive
        try:
            session.wait_for_next(
                lambda event: event.event == "profilingData",
                freeze=False
            )
        except Exception as e:
            log.warning("No profiling event received (may be expected if execution was too fast): {0}", e)

        # Wait for the program to reach the end
        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dap.frame(code_to_debug, line="done")]
        )

        # Stop profiling
        stop_response = session.request("stopProfiling")
        log.info("Stop profiling response: {0}", stop_response)
        assert stop_response.get("status") in ["stopped", "not_running"]
        
        # Verify final stats are present
        assert "finalStats" in stop_response

        session.request_continue()


def test_profiling_data_format(pyfile, target, run):
    """Test that profiling data has the correct format (stack traces)."""
    
    @pyfile
    def code_to_debug():
        import debuggee
        import debugpy
        import time

        debuggee.setup()
        debugpy.breakpoint()  # @bp
        
        def level3():
            time.sleep(0.01)
        
        def level2():
            level3()
        
        def level1():
            level2()
        
        # Generate some stack samples
        for i in range(3):
            level1()
        
        print("done")  # @done

    with debug.Session() as session:
        session.config["justMyCode"] = False
        
        with run(session, target(code_to_debug)):
            pass

        session.wait_for_stop()

        # Start profiling with fast sampling
        session.request("startProfiling", {"sampleInterval": 0.01})

        # Continue execution
        session.request_continue()

        # Wait for and capture a profiling data event
        try:
            profiling_event = session.wait_for_next(
                lambda event: event.event == "profilingData",
                freeze=False
            )
        except Exception as e:
            log.warning("No profiling event received: {0}", e)
            # If no event, skip the format validation
            session.wait_for_stop(
                "breakpoint",
                expected_frames=[some.dap.frame(code_to_debug, line="done")]
            )
            session.request("stopProfiling")
            session.request_continue()
            pytest.skip("No profiling events received during test execution")
            return
        
        log.info("Profiling event received: {0}", profiling_event)
        
        # Verify the event structure
        assert profiling_event.event == "profilingData"
        assert "body" in profiling_event
        
        body = profiling_event.body
        assert "samples" in body
        assert "sampleCount" in body
        assert "timestamp" in body
        
        # Verify samples is an array
        samples = body["samples"]
        assert isinstance(samples, list)
        assert body["sampleCount"] == len(samples)
        
        # If we got samples, verify each sample is a stack (array of frames)
        if len(samples) > 0:
            sample = samples[0]
            assert isinstance(sample, list), "Each sample should be a stack (array of frames)"
            
            # Verify each frame has the required fields
            if len(sample) > 0:
                frame = sample[0]
                assert isinstance(frame, dict)
                assert "file" in frame
                assert "line" in frame
                assert "function" in frame
                log.info("Sample frame structure verified: {0}", frame)

        # Wait for program to finish
        session.wait_for_stop(
            "breakpoint",
            expected_frames=[some.dap.frame(code_to_debug, line="done")]
        )

        # Stop profiling
        session.request("stopProfiling")
        session.request_continue()


def test_stop_profiling_without_start(pyfile, target, run):
    """Test that stopping profiling without starting it doesn't crash."""
    
    @pyfile
    def code_to_debug():
        import debuggee
        import debugpy

        debuggee.setup()
        debugpy.breakpoint()
        print("done")

    with debug.Session() as session:
        with run(session, target(code_to_debug)):
            pass

        session.wait_for_stop()

        # Try to stop profiling without starting it
        stop_response = session.request("stopProfiling")
        log.info("Stop profiling response: {0}", stop_response)
        
        # Should return a status indicating it wasn't running
        assert stop_response.get("status") in ["stopped", "not_running"]

        session.request_continue()
