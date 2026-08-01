# Scientific references for the deterministic ruleset

The 32 rules in `rulesets/ntruth-core-0.1.0.json` cite stable identifiers `R01` through
`R06`. Their complete, machine-readable records live in
`rulesets/scientific-references-0.1.0.json`; tests fail if a rule cites an unknown ID.

These references support rule rationales and terminology. They do not make the current
mapping scientifically approved: the entire ruleset and its 10/17/5 classification
remain `candidate_pending_external_review` until a biostatistician and an independent
wet-lab reviewer sign the review record.

## Registry

| ID | Source | Role in N-Truth |
|---|---|---|
| R01 | Lazic SE, Clarke-Williams CJ, Munafò MR (2018), [What exactly is N in cell culture and animal experiments?](https://doi.org/10.1371/journal.pbio.2005282), PLOS Biology 16(4):e2005282 | Primary empirical/conceptual source for experimental-unit and pseudoreplication rationales. |
| R02 | NC3Rs EDA, [Experimental unit](https://eda.nc3rs.org.uk/index.php/experimental-design-unit) | Official EDA definitions and examples, including multiple experimental units. |
| R03 | NC3Rs, [The DRIVER recommendations: Improving the quality of in vitro research](https://nc3rs.org.uk/news/driver-recommendations-improving-quality-vitro-research), 23 July 2026 | Official announcement and scope of DRIVER. |
| R04 | NC3Rs, [DRIVER recommendations - About](https://nc3rs.org.uk/3rs-resources/driver-recommendations/about) | Official description and boundaries of DRIVER. |
| R05 | NC3Rs, [Terms and conditions](https://nc3rs.org.uk/terms-and-conditions) | Reuse, attribution and non-endorsement boundary. |
| R06 | NC3Rs EDA, [Experimental design resources](https://eda.nc3rs.org.uk/experimental-design) | External graph-based design and terminology reference for in-vivo examples. |

## Interpretation and intellectual-property boundary

- R01 is a scholarly article. Cite the DOI and inspect the article-level license and
  third-party notices before reusing content beyond citation.
- R02-R06 are official NC3Rs/EDA web resources. N-Truth links to and briefly
  paraphrases concepts; it does not reproduce their graphics, wording or branded
  materials.
- The [NC3Rs terms](https://nc3rs.org.uk/terms-and-conditions) restrict reproduction
  and prohibit implied endorsement. N-Truth is an independent companion, not an
  NC3Rs product and not a DRIVER certification service.
- A reference attached to a rule means “source consulted for rationale”, not “the
  source authors approved this exact executable rule, severity or alert class”.

## Rule-to-source mapping

The authoritative mapping is embedded in each rule's `references` array. Reviewers can
inspect it with:

```bash
uv run ntruth rules show MIC-004
uv run python -c 'import json; p=json.load(open("rulesets/ntruth-core-0.1.0.json")); print({r["rule_id"]: r["references"] for r in p["rules"]})'
```

Any new reference requires a versioned registry entry with responsible entity, stable
URL/DOI, access date, rights/terms and intended evidentiary role. Any new or changed
rule still requires the fixtures and external review described in
[CONTRIBUTING.md](../CONTRIBUTING.md).
