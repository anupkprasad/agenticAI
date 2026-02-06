"""Quick test to verify PDB analyzer can load the file"""
import sys
import os

# Add project to path
sys.path.insert(0, '/home/akp66103/workspace/agenticAI')

from src.utils.pdb_analyzer import analyze_pdb

# Test with the actual PDB file
pdb_path = "working_dir/3.pdb"

print(f"Testing PDB analysis on: {pdb_path}")
print(f"File exists: {os.path.exists(pdb_path)}")
print(f"Absolute path: {os.path.abspath(pdb_path)}")
print("=" * 80)

result = analyze_pdb.invoke({"pdb_file": pdb_path})

print(f"\nSuccess: {result.get('success')}")

if result.get('success'):
    analysis = result.get('analysis', {})
    print(f"\n✅ Analysis Results:")
    print(f"  Total atoms: {analysis.get('total_atoms', 0)}")
    print(f"  Total residues: {analysis.get('total_residues', 0)}")
    print(f"  Has protein: {analysis.get('protein', {}).get('present', False)}")
    print(f"  Has ligand: {analysis.get('ligands', {}).get('present', False)}")
    print(f"  Chains: {analysis.get('chain_ids', [])}")
    
    if analysis.get('protein', {}).get('present'):
        protein = analysis['protein']
        print(f"\n  Protein details:")
        print(f"    Total atoms: {protein.get('total_atoms', 0)}")
        print(f"    Total residues: {protein.get('total_residues', 0)}")
        print(f"    Chains: {list(protein.get('chains', {}).keys())}")
        
    if analysis.get('ligands', {}).get('present'):
        ligands = analysis['ligands']
        print(f"\n  Ligand details:")
        print(f"    Total atoms: {ligands.get('total_atoms', 0)}")
        print(f"    Residue names: {ligands.get('residue_names', [])}")
else:
    print(f"\n❌ Analysis Failed:")
    print(f"  Error: {result.get('error', 'Unknown error')}")
    if result.get('details'):
        print(f"\n  Details:\n{result.get('details')}")
