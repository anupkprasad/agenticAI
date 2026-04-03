documentation:  https://docs.google.com/document/d/1C1vGn1YC21VQv6sutrSS050CTJNziNZhu-sEKRBYru0/edit?tab=t.0




###########################################
Take ligand structure ligand.pdb only  (or ligand.mol2 contain charge info). Ligand can be parameterized by Acpype (installed on local system or ACPYPE server (https://bio2byte.be/acpype/) which will generate many files where these two files ligand_GMX.gro and ligand_GMX.itp are required.
The ligand force field should be compatible with the protein force field. The ACPYPE use by default GAFF (General Amber force field) which is compatible with AMBER (ff14SB, ff19SB)
ACPYPE → GAFF/GAFF2 + AM1-BCC charges, converted into GROMACS format
So when you created ligand.itp with the default FF then use “pdb2gmx -ff amber99sb-ildn” for protein

