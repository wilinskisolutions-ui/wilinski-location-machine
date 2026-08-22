# Network allowlist

## The situation

Claude Code sessions for this project run in a managed remote environment whose outbound
HTTPS goes through a policy-enforcing egress proxy. **Verified 2026-08-22:** the proxy
returns `403` on `CONNECT` for every government data host this project needs.

Tested and denied:

```
api.census.gov  www2.census.gov  hazards.fema.gov  www.ncei.noaa.gov
api.bls.gov     aqs.epa.gov      files.zillowstatic.com
overpass-api.de www.countyhealthrankings.org
```

Reachable: PyPI (`pypi.org`, `files.pythonhosted.org`) and the GitHub MCP tools. So the
pipeline can be **built and tested** in-session against fixtures today; only the downloads
are blocked.

Diagnose at any time with:

```bash
curl -sS "$HTTPS_PROXY/__agentproxy/status"
```

`recentRelayFailures` names each denied host and the reason.

## Hosts to allow

Add these to the environment's network policy. Grouped by what breaks without them.

**Universe and demographics — required for Phase 1; nothing runs without these**
```
api.census.gov
www2.census.gov
www.census.gov
```

**Core indicators — required for Phase 2**
```
hazards.fema.gov            www.ncei.noaa.gov         aqs.epa.gov
api.bls.gov                 download.bls.gov          www.bls.gov
apps.bea.gov                www.bea.gov
www.countyhealthrankings.org
www.huduser.gov             files.zillowstatic.com    www.zillow.com
www.fhfa.gov                www.ers.usda.gov
```

**Extended indicators**
```
cde.ucr.cjis.gov            nces.ed.gov               educationdata.urban.org
www.dol.gov                 data.hrsa.gov             data.cms.gov
broadbandmap.fcc.gov        www.transtats.bts.gov     www.transit.dot.gov
overpass-api.de             www.eia.gov               taxfoundation.org
```

**Sensitive layer and hype diagnostic**
```
dataverse.harvard.edu       www.thearda.com           www.irs.gov
```

## How to change it

In claude.ai → the environment for this project → network policy. See
https://code.claude.com/docs/en/claude-code-on-the-web for how environments and network
policies are configured.

## This is an accelerator, not a dependency

Every ingest module is written to run identically whether it is executed in a session or
on a laptop:

- Sources are read through one fetch helper that respects `HTTPS_PROXY` and writes to
  `data/raw/` with a manifest entry.
- If a host is unreachable, the module fails with the host name and the manifest path it
  expected — never with a silent skip or a partial file.
- `make data` is re-runnable and resumes: already-manifested files with matching checksums
  are not re-downloaded.

So the fallback is always available: run `make data` anywhere with open network access and
commit `data/raw/MANIFEST.json` plus the processed parquet files. Nothing about the
pipeline assumes a particular machine.
