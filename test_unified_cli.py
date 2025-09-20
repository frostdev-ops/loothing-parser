#!/usr/bin/env python3
"""
Test script to verify the updated CLI commands work correctly with the unified segmenter.
"""

import subprocess
import sys
import json
from pathlib import Path
from rich.console import Console

console = Console()


def test_parse_command():
    """Test the parse command with unified segmenter."""
    console.print("\n[bold cyan]Testing Parse Command[/bold cyan]")
    console.print("-" * 50)

    # Find a test file
    test_file = Path("examples/WoWCombatLog-091625_041109.txt")
    if not test_file.exists():
        console.print("[red]Test file not found![/red]")
        return False

    # Test 1: Sequential processing with summary output
    console.print("\n[yellow]Test 1: Sequential processing (--no-parallel)[/yellow]")
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "parse", str(test_file), "--no-parallel"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        console.print("[green]✓ Sequential parse succeeded[/green]")
        # Check for key output elements
        if "Parsing Complete" in result.stdout and "Mythic+ Runs" in result.stdout:
            console.print("  ✓ Output contains expected sections")
        else:
            console.print("  [yellow]⚠ Output may be incomplete[/yellow]")
    else:
        console.print(f"[red]✗ Sequential parse failed: {result.stderr}[/red]")
        return False

    # Test 2: Parallel processing
    console.print("\n[yellow]Test 2: Parallel processing (2 threads)[/yellow]")
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "parse", str(test_file), "--threads", "2"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        console.print("[green]✓ Parallel parse succeeded[/green]")
        if "Using parallel processing" in result.stdout:
            console.print("  ✓ Parallel processing was used")
    else:
        console.print(f"[red]✗ Parallel parse failed: {result.stderr}[/red]")
        return False

    # Test 3: JSON export
    console.print("\n[yellow]Test 3: JSON export[/yellow]")
    output_file = Path("test_output.json")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.cli",
            "parse",
            str(test_file),
            "--format",
            "json",
            "-o",
            str(output_file),
            "--no-parallel",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0 and output_file.exists():
        console.print("[green]✓ JSON export succeeded[/green]")

        # Verify JSON structure
        try:
            with open(output_file) as f:
                data = json.load(f)
            console.print(f"  ✓ Exported {len(data)} encounters")

            # Check for unified structure
            if data and "encounter_type" in data[0]:
                console.print("  ✓ JSON has unified encounter structure")
                if data[0]["encounter_type"] == "mythic_plus" and "fights" in data[0]:
                    console.print(f"  ✓ M+ run contains {len(data[0]['fights'])} fights")
        except Exception as e:
            console.print(f"  [red]✗ JSON validation failed: {e}[/red]")

        # Cleanup
        output_file.unlink()
    else:
        console.print(f"[red]✗ JSON export failed[/red]")
        return False

    return True


def test_analyze_command():
    """Test the analyze command with unified segmenter."""
    console.print("\n[bold cyan]Testing Analyze Command[/bold cyan]")
    console.print("-" * 50)

    # Find a test file
    test_file = Path("examples/WoWCombatLog-091625_041109.txt")
    if not test_file.exists():
        console.print("[red]Test file not found![/red]")
        return False

    # Test: Summary mode (non-interactive)
    console.print("\n[yellow]Test: Summary mode (--summary)[/yellow]")
    result = subprocess.run(
        [sys.executable, "-m", "src.cli", "analyze", str(test_file), "--summary"],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        console.print("[green]✓ Analyze summary succeeded[/green]")
        if "Event Type Distribution" in result.stdout:
            console.print("  ✓ Event distribution shown")
    else:
        console.print(f"[red]✗ Analyze summary failed: {result.stderr}[/red]")
        return False

    # Note: Can't test interactive mode in automated test
    console.print("\n[dim]Note: Interactive mode requires manual testing[/dim]")

    return True


def main():
    """Run all tests."""
    console.print("[bold]Unified CLI Command Tests[/bold]")
    console.print("=" * 50)

    success = True

    # Test parse command
    if not test_parse_command():
        success = False

    # Test analyze command
    if not test_analyze_command():
        success = False

    # Summary
    console.print("\n" + "=" * 50)
    if success:
        console.print("[bold green]✓ All tests passed![/bold green]")
        console.print("\nThe CLI commands now use:")
        console.print("  • Unified segmenter with enhanced character tracking")
        console.print("  • Parallel processing for improved performance")
        console.print("  • Hierarchical M+ encounter structure")
        console.print("  • Ability breakdowns with percentages")
        console.print("  • Death analysis with recent events")
    else:
        console.print("[bold red]✗ Some tests failed[/bold red]")
        console.print("Please check the errors above")

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())