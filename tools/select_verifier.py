#!/usr/bin/env python3
"""Capability-aware verifier selection for intent-verify.

Picks a verifier model that is (a) not the implementer, (b) at or above the
capability floor for the change's complexity, (c) preferably from a different
vendor family, and decides the dispatch mode (FULL vs STRUCTURED). Among the
candidates that pass, it prefers the fastest one this plugin's benchmark has
timed (verify_seconds in the registry); for a complex change, or with
--prefer capable, the most capable. On the one task where both were run, the
most capable candidate and the timed one returned the same verdict; what
differed was the wait. In the first real run the most capable candidate
verified for nine minutes, and the timed one takes seconds on the benchmark's
fixtures. A model the index does not list yet has no score to rank by; its
registry row may name the listed model it ranks just above (ranks_above), and
the output says when a pick rests on that. Encodes the
policy in skills/intent-verify/SKILL.md against models/registry.json — usable
as a CLI by the orchestrating agent or imported by the benchmark harness.

Usage:
  python3 tools/select_verifier.py --implementer claude-opus-5-5 \
      --candidates sonnet opus fable haiku \
      [--complexity simple|standard|complex] [--prefer fast|capable]
      [--registry models/registry.json]

Output: one JSON object on stdout:
  {"verifier": id|null, "mode": "FULL"|"STRUCTURED"|null, "tier": ...,
   "warnings": [...], "reason": "...", "ranked": [...]}
Exit codes: 0 selection made; 3 no eligible candidate (fallback guidance in
"reason"); 2 usage error. Never guesses a tier for unknown models — unknowns
are excluded with a warning unless --assume-tier is given.
"""
import argparse
import json
import os
import sys

DEFAULT_REGISTRY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "registry.json")
TIER_ORDER = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}


def norm(s):
    return s.strip().lower().replace(" ", "-").replace("_", "-").replace(".", "-") if s else s


def load_registry(path):
    with open(path, encoding="utf-8") as f:
        reg = json.load(f)
    index = {}
    for m in reg["models"]:
        index[norm(m["id"])] = m
        for a in m.get("aliases", []):
            index.setdefault(norm(a), m)
    return reg, index


def tier_of(model, bounds):
    if model.get("tier"):
        return model["tier"]
    score = model.get("aa_intelligence")
    if score is None:
        return None
    for t in ("T1", "T2", "T3"):
        if score >= bounds[t]:
            return t
    return "T4"


def resolve(name, index):
    return index.get(norm(name))


def select(implementer, candidates, complexity, reg, index, assume_tier=None, prefer=None):
    prefer = prefer or ("capable" if complexity == "complex" else "fast")
    warnings, out_ranked = [], []
    bounds = reg["tier_bounds"]
    floor = reg["floor_by_complexity"][complexity]
    max_gap = reg.get("max_gap_below_implementer", 25)

    impl = resolve(implementer, index) if implementer else None
    if implementer and not impl:
        warnings.append(f"implementer '{implementer}' not in registry; gap check skipped")
    impl_score = (impl or {}).get("aa_intelligence")
    impl_family = (impl or {}).get("family")
    impl_id = (impl or {}).get("id", norm(implementer) if implementer else None)

    eligible = []
    for name in candidates:
        m = resolve(name, index)
        if not m:
            if assume_tier:
                m = {"id": norm(name), "family": "unknown", "aa_intelligence": None, "tier": assume_tier}
                warnings.append(f"candidate '{name}' not in registry; using --assume-tier {assume_tier}")
            else:
                warnings.append(f"candidate '{name}' not in registry; excluded (add it, or pass --assume-tier)")
                continue
        t = tier_of(m, bounds)
        entry = {"id": m["id"], "tier": t, "score": m.get("aa_intelligence"), "family": m.get("family")}
        if m.get("verify_seconds") is not None:
            entry["verify_seconds"] = m["verify_seconds"]
        if m.get("aa_intelligence") is None and m.get("ranks_above"):
            entry["ranks_above"] = m["ranks_above"]
        if m["id"] == impl_id:
            entry["excluded"] = "same model as implementer"
        elif t is None:
            entry["excluded"] = "unknown tier"
        elif t == "T4":
            entry["excluded"] = "below absolute floor (T4): failure modes include fabricated evidence and broken ledgers"
        elif TIER_ORDER[t] > TIER_ORDER[floor]:
            entry["excluded"] = f"below capability floor {floor} required for '{complexity}' changes"
        out_ranked.append(entry)
        if "excluded" not in entry:
            eligible.append((m, t, entry))

    if not eligible:
        return {
            "verifier": None, "mode": None, "tier": None, "warnings": warnings, "ranked": out_ranked,
            "reason": ("no eligible cross-model verifier at or above the floor; fall back to same-model "
                       "fresh-context verification and state that the cross-model lever was lost"),
        }

    def other_family(m):
        """Known to come from another vendor family. A candidate the registry does
        not list has no known family, and unknown is not different: it used to be
        preferred over every listed model of the implementer's family."""
        return bool(impl_family) and m.get("family") not in (None, "unknown", impl_family)

    def capability(m):
        """The published score. A model the index does not list yet has none; if
        its registry row names a listed model it ranks above, it is placed just
        above that one and below everything scored higher."""
        score = m.get("aa_intelligence")
        if score is None and m.get("ranks_above"):
            below = (resolve(m["ranks_above"], index) or {}).get("aa_intelligence")
            return below + 0.1 if below is not None else 0.0
        return score or 0.0

    def rank_key(item):
        m, t, _ = item
        diff_family = 0 if other_family(m) else 1
        score = capability(m)
        seconds = m.get("verify_seconds")
        if prefer == "fast":
            # Timed candidates first, fastest first; the rest by capability.
            return (diff_family, seconds is None, seconds or 0.0, -score)
        return (diff_family, -score)

    eligible.sort(key=rank_key)
    chosen, chosen_tier, chosen_entry = eligible[0]
    chosen_entry["selected"] = True

    if impl_family and chosen.get("family") == impl_family:
        warnings.append("no different-family candidate was eligible; verifier shares the implementer's family "
                        "(cross-model lever weakened)")
    chosen_score = chosen.get("aa_intelligence")
    if chosen_score is None:
        warnings.append("verifier has no published score (explicit tier only); treat capability margin as unknown"
                        + ("; it is ranked above %s by the registry's assumption, not by a measurement" % chosen["ranks_above"]
                           if chosen.get("ranks_above") else ""))
    if impl_score is not None and chosen_score is not None and impl_score - chosen_score > max_gap:
        warnings.append(f"weak-verifier: verifier is {impl_score - chosen_score:.1f} points below the implementer "
                        f"(gap cap {max_gap}); attach this warning to the verification report")

    mode = "STRUCTURED" if chosen_tier == "T3" else "FULL"
    return {
        "verifier": chosen["id"], "mode": mode, "tier": chosen_tier, "warnings": warnings, "ranked": out_ranked,
        "reason": (("fastest eligible candidate the benchmark has timed (%.1f s a verification)" % chosen["verify_seconds"]
                    if prefer == "fast" and chosen.get("verify_seconds") is not None
                    else "highest-capability eligible candidate")
                   + (", different-family preference applied" if other_family(chosen)
                      else " (same/unknown family)")),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--implementer", help="model that wrote the change")
    p.add_argument("--candidates", nargs="+", required=True, help="models available to run the verifier on")
    p.add_argument("--complexity", choices=["simple", "standard", "complex"], default="standard")
    p.add_argument("--registry", default=DEFAULT_REGISTRY)
    p.add_argument("--assume-tier", choices=["T1", "T2", "T3"], help="tier to assume for candidates missing from the registry")
    p.add_argument("--prefer", choices=["fast", "capable"],
                   help="among eligible candidates: the fastest one the benchmark has timed, or the most capable "
                        "(default: capable for a complex change, fast otherwise)")
    a = p.parse_args(argv)
    reg, index = load_registry(a.registry)
    result = select(a.implementer, a.candidates, a.complexity, reg, index, a.assume_tier, a.prefer)
    print(json.dumps(result, indent=2))
    return 0 if result["verifier"] else 3


if __name__ == "__main__":
    sys.exit(main())
