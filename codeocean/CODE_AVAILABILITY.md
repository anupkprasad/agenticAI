# Code availability (draft for manuscript)

**Suggested statement** (edit URLs/DOIs after deposit):

> The SimAgent source code supporting this study is available at
> https://github.com/anupkprasad/agenticAI under the MIT License, frozen for
> this manuscript on branch `SimAgent_v1.0` (commit \<SHA\>). A Code Ocean
> compute capsule provides a cloud-executable smoke test and regenerates an
> example feature-matrix figure from deposited tables
> (DOI: \<Code-Ocean-DOI-when-published\>). Full MD campaigns require a local
> conda environment (`environment.yml`), optional Ollama or an LLM API key, and
> SLURM access as described in the repository README; published agent provenance
> (without trajectories) is archived under
> `campaigns/robustness/simagent_provenance/`.

## Checklist before submission

- [ ] Push branch `SimAgent_v1.0` to GitHub
- [ ] Record commit SHA: `git rev-parse HEAD`
- [ ] Create Code Ocean capsule; Reproducible Run = `bash codeocean/run`
- [ ] After Code Ocean verification, paste private share link for editors
- [ ] On acceptance, replace `<Code-Ocean-DOI-when-published>` and cite the capsule
- [ ] Optional: Zenodo archive of the same tag/branch for a second DOI
