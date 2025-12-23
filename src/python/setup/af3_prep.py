import sys
import os
sys.path.append('/home/anup/myScripts/machineLearning/alphaFold3')
import AF3MSA
from inputPrepAF3 import generateAF3InputJson, customMSA
from Bio import SeqIO

#### variables for Custom MSA and AF3 input generation ####
path = "/mnt/mydrive/pseudokinase/pseudoNcontrol_AF3/other_donors"
queryFile = "all.fasta"
ligand = "ADP"

# Extract the amino acid sequence as a string
uprot_list = []
record = SeqIO.parse(path + "/" + queryFile, "fasta")
for i, seq_record in enumerate(record):
    if  i > -1:
        print(i)
        uprotid = str(seq_record.id).split("_")[0]
        if uprotid[-3:] == "KD2":
            kd = "KD2"
        else:
            kd = "KD1"

        # uprotid = str(seq_record.id).split("|")[1]
        # kdtype = str(seq_record.id).split("|")[0]
        # if "Dom1" in kdtype:
        #     kd = "KD1"
        # elif "Dom2" in kdtype:
        #     kd = "KD2"
        # else:
        #     kd = "2MG"

        sequence = str(seq_record.seq)
        query = ligand + "_" + uprotid[1:] + "_" + kd + "_"
        print(f"{query}")
        uprot_list.append(query)

        ######Looping all rest

        msaTargetFile = "DCLK.fasta"
        msaDepth = 'DCLK'
        msaDepths = [msaDepth, 'F', 'A']
        msaDepths = ["A"]
        temps = ["A"] ##  A,C,F : A=AF3-searched template, C=custom template, F=template free
        #temps = [""]
        seeds = list(range(0, 4000, 100))

        PTMs = [
        #{"type": "TPO", "position": 273},
        # {"type": "TPO", "position": 264},
        # {"type": "SEP", "position": 276},
        # {"type": "SEP", "position": 277},
        # {"type": "SEP", "position": 283}
        ]






        ######### No need to change below this line #########

        ##### MSA Generation using JackHMMER #####
        if msaDepths != ["A"]:
            msa_output = os.path.join(path, query + "_" + msaDepth +  "_msa.fasta")
            AF3MSA.run_jackhmmer(
                query_fasta= os.path.join(path, queryFile ),
                database_fasta= os.path.join(path, msaTargetFile),
                output_sto= msa_output.replace(".fasta", ".sto"),
                iterations=3,)
            AF3MSA.sto_to_fasta(msa_output.replace(".fasta", ".sto"), msa_output)
            AF3MSA.fasta_to_GapRemoved_a3m(msa_output, msa_output.replace(".fasta", ".a3m"))





        #### AF3 input generation ####
        for msa in msaDepths:
            for temp in temps:
                if msa != "A":
                    sequence, oneline_msa = customMSA(os.path.join (path , query + "_" + msaDepth + "_msa.a3m"))
                    print("Sequence length: ", len(sequence))
                if msa == msaDepth and temp == "A":
                    unpaired_msa, paired_msa = oneline_msa, ""
                    templates = None
                elif msa ==msaDepth and temp == "F":
                    unpaired_msa, paired_msa = oneline_msa, ""
                    templates = []
                elif msa == "F" and temp =="A":
                    unpaired_msa, paired_msa = "", ""
                    templates = None
                elif msa == "F" and temp == "F":
                    unpaired_msa, paired_msa = "", ""
                    templates = []
                elif msa == "A" and temp == "A":
                    unpaired_msa, paired_msa = None, None
                    templates = None
                elif msa == "A" and temp == "F":
                    continue
                
                ptm_name = ""
                if PTMs != []:
                    ptm_name = "p" + 'p'.join([str(ptm["position"]) for ptm in PTMs])


                generateAF3InputJson(
                    name= query + ptm_name + "_" + msa + "msa" + "_" + temp + "temp", 
                    sequence=sequence,
                    PTMs=PTMs,
                    model_seeds=seeds,
                    unpaired_msa= unpaired_msa,
                    paired_msa= paired_msa,
                    templates= templates,
                    output_file= os.path.join(path + "/", query + ptm_name + "_" + msa + "msa" + "_" + temp + "temp_af3.json"),
                    ligand=ligand,
                )
