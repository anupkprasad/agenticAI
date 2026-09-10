#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on 2025-07-30 (Y/M/D) at 10:54
@author: Anup K. Prasad
email: anupkprasad121@gmail.com
"""

import sys
sys.path.append("/home/anup/myScripts")
from bioinformatics.sequence.uniProtApi import getUniprotIds, getUniprotSequence, saveFastaKDnfullLength, get_uniprot_pseudokinases

import pandas as pd
import numpy as np


path = "/mnt/mydrive/pseudokinase"
# pseudoK_id = pd.read_csv(path + "/human_pseudokinases_uids.txt")
# pseudoK_id = np.array(pseudoK_id).flatten()

pseudoK_id = [
    "O60229",
    "O75116",
    "O75962",
    "O94804",
    "P16066",
    "P20594",
    "P35790",
    "P42356",
    "Q02763",
    "Q02846",
    "Q13237",
    "Q13546",
    "Q6J9G0",
    "Q6JQN1",
    "Q6P3W7",
    "Q6ZWH5",
    "Q709F0",
    "Q7L7X3",
    "Q8N2I9",
    "Q8NE63",
    "Q8NEV4",
    "Q8TD19",
    "Q8WXR4",
    "Q8WZ42",
    "Q96J92",
    "Q96Q04",
    "Q9BYP7",
    "Q9H2G2",
    "Q9H2K8",
    "Q9H4A3",
    "Q9H5K3",
    "Q9HBU6",
    "Q9NVF9",
    "Q9P2K8",
    "Q9Y259",
    "Q9Y2H9",
    "Q9Y3S1",
    "Q9Y6S9"
  ]

result = []
need_manual_check = []
for i, uniprot_id in enumerate(pseudoK_id):
    print(f"Fetching sequence for {uniprot_id} ({i+1}/{len(pseudoK_id)})")
    seq_data = getUniprotSequence(uniprot_id)
    if seq_data.get('kinase_domains') == []:
        print(f"No kinase domain found for {uniprot_id}, skipping...")
        need_manual_check.append(uniprot_id)
        continue
    result.append(getUniprotSequence(uniprot_id))

saveFastaKDnfullLength(result, filePrefix=path + "/functional_kinase_missing_keyRes")

