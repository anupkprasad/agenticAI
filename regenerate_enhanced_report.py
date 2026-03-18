#!/usr/bin/env python3
"""
Regenerate HTML Report with Enhanced Features

This script regenerates the HTML report from existing analysis data
with the new enhanced features (embedded images, key statistics).
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, '/home/akp66103/workspace/agenticAI')

def regenerate_report():
    """Regenerate HTML report with enhanced features"""
    import json
    from src.reporter.html_generator import build_html_content
    
    # Paths
    working_dir = Path("/home/akp66103/workspace/agenticAI/working_dir")
    analysis_dir = working_dir / "analysis"
    reporter_dir = working_dir / "reporter"
    summary_file = analysis_dir / "analysis_summary.jsonl"
    
    print("=" * 80)
    print("Regenerating HTML Report with Enhanced Features")
    print("=" * 80)
    
    # Read analysis data manually
    print("\n1. Reading analysis summary...")
    
    if not summary_file.exists():
        print(f"   ✗ Analysis summary not found: {summary_file}")
        return False
    
    # Parse JSONL file
    entries = []
    with open(summary_file, 'r') as f:
        content = f.read()
    
    # Handle pretty-printed JSON blocks separated by "---"
    blocks = [b.strip() for b in content.split('---') if b.strip()]
    for block in blocks:
        try:
            entry = json.loads(block)
            # Skip header/metadata block
            if "summary_file_version" not in entry and "analysis_type" in entry:
                entries.append(entry)
        except json.JSONDecodeError:
            pass
    
    # Summarize analysis types
    analysis_types = {}
    for entry in entries:
        atype = entry.get("analysis_type", "unknown")
        analysis_types[atype] = analysis_types.get(atype, 0) + 1
    
    result = {
        "success": True,
        "entries": entries,
        "analysis_types": list(analysis_types.keys()),
        "total_entries": len(entries)
    }
    
    print(f"   ✓ Loaded {result.get('total_entries', 0)} analysis entries")
    print(f"   ✓ Analysis types: {', '.join(result.get('analysis_types', []))}")
    
    # Generate HTML report
    print("\n2. Generating enhanced HTML report...")
    
    output_file = "kinase_enhanced_report.html"
    output_path = reporter_dir / output_file
    
    html_content = build_html_content(
        analysis_data=result,
        literature_refs=[],
        report_type="comprehensive"
    )
    
    # Write to file
    reporter_dir.mkdir(exist_ok=True, parents=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    file_size_kb = output_path.stat().st_size / 1024
    
    print(f"   ✓ Report created: {output_file}")
    print(f"   ✓ File size: {file_size_kb:.1f} KB")
    print(f"   ✓ Location: {output_path}")
    
    # Count embedded images
    image_count = html_content.count('data:image')
    
    print("\n3. Report features:")
    print(f"   📊 Embedded images: {image_count}")
    print(f"   📈 Analysis sections: {result.get('total_entries', 0)}")
    print(f"   🎨 Modern styling: Yes")
    print(f"   📱 Responsive layout: Yes")
    
    print(f"\n✓✓✓ Success! ✓✓✓")
    print(f"\nView your enhanced report at:")
    print(f"  file://{output_path}")
    
    print(f"\nComparison:")
    old_report = reporter_dir / "kinase_report.html"
    if old_report.exists():
        old_size_kb = old_report.stat().st_size / 1024
        print(f"  Old report: {old_size_kb:.1f} KB (text only)")
        print(f"  New report: {file_size_kb:.1f} KB (with embedded images)")
        print(f"  Increase: {file_size_kb - old_size_kb:.1f} KB ({((file_size_kb/old_size_kb - 1) * 100):.0f}%)")
    
    return True


if __name__ == "__main__":
    try:
        print("\n")
        success = regenerate_report()
        print("\n")
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
