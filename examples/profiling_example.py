#!/usr/bin/env python3
"""
Example demonstrating debugpy profiling support.

This script can be debugged in VSCode, and profiling can be controlled
via the DAP protocol (once VSCode extension support is added).
"""

import time


def fibonacci(n):
    """Calculate fibonacci number (inefficient recursive version for profiling demo)."""
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


def process_batch(size):
    """Process a batch of fibonacci calculations."""
    results = []
    for i in range(size):
        result = fibonacci(15)
        results.append(result)
    return results


def main():
    """Main application that does some work worth profiling."""
    print("Starting application...")
    print("This application can be profiled when running under debugpy.")
    print()
    print("To use profiling:")
    print("1. Set a breakpoint below")
    print("2. Run with debugging in VSCode")
    print("3. When paused, use the (future) 'Start Profiling' button")
    print("4. Continue execution")
    print("5. View live flame graph of execution")
    print()
    
    # Set a breakpoint here to start profiling before this code runs
    input("Press Enter to start processing (set breakpoint here)...")
    
    print("Processing batches...")
    for batch_num in range(5):
        print(f"  Batch {batch_num + 1}/5")
        results = process_batch(10)
        time.sleep(0.1)
    
    print()
    print("Done! If profiling was active, you should see:")
    print("- Flame graph showing fibonacci() calls dominating")
    print("- Call stacks from main -> process_batch -> fibonacci")
    print("- Recursive fibonacci calls visible in the graph")
    
    # Set a breakpoint here to stop profiling after the work is done
    input("Press Enter to exit (set breakpoint here to stop profiling)...")


if __name__ == "__main__":
    main()
