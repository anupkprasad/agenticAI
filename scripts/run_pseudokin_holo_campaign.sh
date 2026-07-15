#!/usr/bin/env bash
# Paste-safe launcher for the holo pseudokinase end-to-end campaign.
# Avoids shell backticks inside --goal (they break under double quotes).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WORKDIR="./pseudoKin_holo"
mkdir -p "$WORKDIR"

# Single-quoted heredoc: no bash expansion of `, $, etc.
GOAL=$(cat <<'EOF'
Run an end-to-end MD campaign for 38 human protein-ATP holo systems in ./pseudoKin_holo (one PDB per UniProt id listed below). For each system: preprocess the structure, set up GROMACS (AMBER99SB-ILDN / TIP3P / 310 K / 1 bar / 0.15 M NaCl), submit ~200 ns production MD to HPC then analyze. Per simulation compute ATP-pocket COM distance, heavy-atom contacts, pocket H-bonds, ligand-axis orientation, residence, pocket RMSF and SASA, Ca PCA, free-energy landscape at 310 K (PC1-PC2), basin features, and basin representative PDBs. After all trajectories finish, run combined analysis: build an MLKL (q8nb16) consensus alignment; map the MLKL ATP pocket (consensus residues within 15 A of ATP at frame 0) to every protein; define bound as COM <= 10 A and >=1 heavy-atom contact; cluster systems with Ward hierarchical clustering (k = 5) on z-scored reference-pocket dynamics plus local FEL descriptors (landscape entropy, major-basin population); make cluster-validation and by-cluster trajectory plots; write a combined HTML report with literature context. UniProt list / id:name map: o15197:EPHB6, o43187:IRAK2, o60674:JAK2, p00533:EGFR, p17612:KAPCA, p21860:ERBB3, p23458:JAK1, p24941:CDK2, p25092:GUC2C, p28482:MK01, p29597:TYK2, p51841:GUC2F, p52333:JAK3, q05823:RN5A, q13308:PTK7, q13418:ILK, q58a45:PAN3, q5jzy3:EPHAA, q6vab6:KSR2, q7rtn6:STRAA, q7z7a4:PXK, q8iv63:VRK3, q8ivt5:KSR1, q8nb16:MLKL, q8ncb2:CAMKV, q8ne28:STKL1, q8tea7:TBCK, q8wz42:TITIN, q92519:TRIB2, q96c45:ULK4, q96qs6:PSKH2, q96s38:KS6C1, q9bxu1:STK31, q9c0k7:STRAB, q9nsy0:NRBP2, q9uhy1:NRBP, q9y243:AKT3, q9y616:IRAK3.
EOF
)

echo "Launching pseudoKin_holo campaign ($(ls -1 "$WORKDIR"/*.pdb | wc -l) PDBs) ..."
nohup python run_agenticAIWork.py \
  --goal "$GOAL" \
  --working-dir "$WORKDIR" \
  --pdb-list "$WORKDIR"/*.pdb \
  --subtask preprocess simsetup hpcjob analysis reporter \
  --simtype multisim \
  --allowed-hpc-jobs 5 \
  --hpc-check-interval 60m \
  --resume \
  > "$WORKDIR/output.log" 2>&1 &

echo "PID $!  log: $WORKDIR/output.log"
echo "tail -f $WORKDIR/output.log"
