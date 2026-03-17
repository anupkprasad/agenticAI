"""
Validation utility for programmer-generated analysis tools

Checks that analysis tools properly include logging to analysis_summary.jsonl
"""
import os
import ast
import logging
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def check_tool_has_logging(tool_path: str) -> Dict[str, any]:
    """
    Check if a Python tool includes proper analysis_summary logging.
    
    Args:
        tool_path: Path to the Python tool file
        
    Returns:
        Dict with validation results
    """
    result = {
        "file": os.path.basename(tool_path),
        "has_summary_import": False,
        "has_append_call": False,
        "has_statistics": False,
        "has_min_max": False,
        "has_output_path_bug": False,  # NEW: Check for common bug
        "issues": []
    }
    
    try:
        with open(tool_path, 'r') as f:
            content = f.read()
        
        # Check for summary_logger import
        if "from src.analysis.summary_logger import append_analysis_summary" in content:
            result["has_summary_import"] = True
        else:
            result["issues"].append("Missing: from src.analysis.summary_logger import append_analysis_summary")
        
        # Check for append_analysis_summary call
        if "append_analysis_summary(" in content:
            result["has_append_call"] = True
        else:
            result["issues"].append("Missing: append_analysis_summary() function call")
        
        # Check for statistics parameter (keyword argument, not string)
        if "statistics=" in content:
            result["has_statistics"] = True
        else:
            result["issues"].append("Missing: statistics parameter in append_analysis_summary()")
        
        # Check for min/max values in statistics
        has_min = "min_" in content or '"min"' in content
        has_max = "max_" in content or '"max"' in content
        if has_min and has_max:
            result["has_min_max"] = True
        else:
            result["issues"].append("Missing: min/max values in statistics")
        
        # NEW: Check for common bug - using _resolve_input_path on output files
        if "_resolve_input_path(output_" in content or "_resolve_input_path(output" in content:
            result["has_output_path_bug"] = True
            result["issues"].append("⚠️ BUG: Using _resolve_input_path() on OUTPUT file - use filename directly!")
        
        # Parse AST to check structure
        try:
            tree = ast.parse(content)
            result["syntax_valid"] = True
        except SyntaxError as e:
            result["syntax_valid"] = False
            result["issues"].append(f"Syntax error: {e}")
        
        # Determine if this looks like an analysis tool
        result["is_analysis_tool"] = any([
            "analysis" in tool_path.lower(),
            "calculate" in content.lower(),
            "MDAnalysis" in content,
            "trajectory" in content.lower(),
            "topology" in content.lower()
        ])
        
        # Overall pass/fail
        if result["is_analysis_tool"]:
            result["passes_validation"] = all([
                result["has_summary_import"],
                result["has_append_call"],
                result["has_statistics"],
                result["has_min_max"],
                not result["has_output_path_bug"]  # Must NOT have this bug
            ])
        else:
            result["passes_validation"] = True  # Non-analysis tools don't need logging
            result["issues"] = []  # Clear issues for non-analysis tools
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to validate {tool_path}: {e}")
        result["issues"].append(f"Validation error: {e}")
        result["passes_validation"] = False
        return result


def validate_all_programmer_tools(programmer_dir: str = "working_dir/programmer") -> List[Dict]:
    """
    Validate all Python tools in the programmer directory.
    
    Args:
        programmer_dir: Directory containing programmer-generated tools
        
    Returns:
        List of validation results
    """
    if not os.path.exists(programmer_dir):
        logger.warning(f"Programmer directory not found: {programmer_dir}")
        return []
    
    results = []
    for filename in os.listdir(programmer_dir):
        if filename.endswith(".py") and not filename.startswith("_"):
            tool_path = os.path.join(programmer_dir, filename)
            result = check_tool_has_logging(tool_path)
            results.append(result)
    
    return results


def print_validation_report(results: List[Dict]) -> None:
    """Print a formatted validation report"""
    print("\n" + "="*80)
    print("PROGRAMMER-GENERATED TOOLS VALIDATION REPORT")
    print("="*80)
    
    analysis_tools = [r for r in results if r["is_analysis_tool"]]
    other_tools = [r for r in results if not r["is_analysis_tool"]]
    
    passing = [r for r in analysis_tools if r["passes_validation"]]
    failing = [r for r in analysis_tools if not r["passes_validation"]]
    
    print(f"\n📊 Summary:")
    print(f"  Total tools: {len(results)}")
    print(f"  Analysis tools: {len(analysis_tools)}")
    print(f"  Other tools: {len(other_tools)}")
    print(f"  ✅ Passing: {len(passing)}")
    print(f"  ❌ Failing: {len(failing)}")
    
    if passing:
        print(f"\n✅ Passing Analysis Tools ({len(passing)}):")
        for r in passing:
            print(f"  • {r['file']}")
    
    if failing:
        print(f"\n❌ Failing Analysis Tools ({len(failing)}):")
        for r in failing:
            print(f"\n  • {r['file']}")
            for issue in r["issues"]:
                print(f"    - {issue}")
    
    if other_tools:
        print(f"\n📝 Other Tools (no logging required): {len(other_tools)}")
        for r in other_tools:
            print(f"  • {r['file']}")
    
    print("\n" + "="*80)
    
    # Return exit code
    return 0 if len(failing) == 0 else 1


if __name__ == "__main__":
    import sys
    
    # Allow custom directory
    programmer_dir = sys.argv[1] if len(sys.argv) > 1 else "working_dir/programmer"
    
    results = validate_all_programmer_tools(programmer_dir)
    exit_code = print_validation_report(results)
    sys.exit(exit_code)
