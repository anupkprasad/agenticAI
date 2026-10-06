# Code availability (draft for manuscript)

**Suggested statement** (edit URLs/DOIs after deposit):

> The SimAgent source code supporting this study is available at
> https://github.com/anupkprasad/agenticAI under the MIT License, frozen for
> this manuscript on branch `SimAgent_v1.0` (commit \<SHA\>). A Code Ocean
> compute capsule (DOI: \<Code-Ocean-DOI-when-published\>) builds the
> `SimAgentEnv` conda environment and regenerates selected summary figures from
> deposited tables taken from the published worked example
> `example/pseudo_apo_holo/`. Ligand parameterization (ACPYPE), GROMACS MD
> system setup and production, Ollama LLM planning, and SLURM/HPC submission
> are computationally intensive relative to a typical cloud capsule; those
> stages are therefore demonstrated via already completed campaign outputs in
> `example/pseudo_apo_holo/` rather than re-executed in Code Ocean. Reviewers
> should inspect the combined HTML report at
> `example/pseudo_apo_holo/reporter/combined_report.html`
> (https://github.com/anupkprasad/agenticAI/blob/SimAgent_v1.0/example/pseudo_apo_holo/reporter/combined_report.html).
> A local re-run guide is provided in `example/TUTORIAL.md`. Paper-scale agent
> provenance (without trajectories) is archived under
> `campaigns/robustness/simagent_provenance/`.

## Checklist before submission

- [ ] Push branch `SimAgent_v1.0` to GitHub
- [ ] Record commit SHA: `git rev-parse HEAD`
- [ ] On Code Ocean: create `SimAgentEnv` from `codeocean/environment/environment.yml`
- [ ] Reproducible Run = `bash codeocean/run`
- [ ] Confirm reviewers are pointed to `example/pseudo_apo_holo/reporter/combined_report.html`
- [ ] After Code Ocean verification, paste private share link for editors
- [ ] On acceptance, replace `<Code-Ocean-DOI-when-published>` and cite the capsule
- [ ] Optional: Zenodo archive of the same tag/branch for a second DOI
