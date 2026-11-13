# compare_deep.py
#
# Aufruf:  python compare_deep.py baseline.csv ast.csv [abweichungen.csv]

import csv, sys

# Dieselben Indikatoren wie in compare.py, aber tests_found zeigt jetzt auf
# die erreichbarkeitsbewusste Spalte.
INDICATORS = [
    ("has_cmake_file",                       "has_cmakelists", ["has_cmakelists"]),
    ("uses_gtest (find_package)",            "uses_gtest",     ["cmake_uses_gtest"]),
    ("uses_catch2 (find_package)",           "uses_catch2",    ["cmake_uses_catch2"]),
    ("tests_found (nur ausgewertete)",       "has_cpp_tests",  ["cmake_tests_reachable"]),
    ("gtests_found (gtest_discover_tests)",  "gtests_found",   ["cmake_gtests_found"]),
]


def as_bool(v):
    if v is None:
        return None
    t = str(v).strip().lower()
    if t == "" or t == "nan":
        return None
    return t == "true"


def as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def load(path):
    rows = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pid = row.get("project_id") or row.get("joss_id") or ""
            if pid:
                rows[pid] = row
    return rows


def any_true(row, columns):
    vals = []
    for c in columns:
        v = as_bool(row.get(c))
        if v is not None:
            vals.append(v)
    if not vals:
        return None
    return any(vals)


def run(baseline, ast_rows, indicators):
    alle_ids = sorted(set(list(baseline.keys()) + list(ast_rows.keys())), key=str)
    abweichungen = []

    for (label, bcol, tcols) in indicators:
        beide_ja = beide_nein = nur_base = nur_ast = keine = halbe = 0

        for pid in alle_ids:
            b = baseline.get(pid, {})
            t = ast_rows.get(pid, {})
            bv = as_bool(b.get(bcol))
            tv = any_true(t, tcols)

            if bv is None and tv is None:
                keine += 1
                continue
            if bv is None or tv is None:
                halbe += 1
                abweichungen.append([label, pid, b.get("repo_url") or t.get("repo_url"),
                                     bv, tv, "eine Seite hat keine Daten"])
                continue
            if bv == tv:
                if bv:
                    beide_ja += 1
                else:
                    beide_nein += 1
                continue
            if bv and not tv:
                nur_base += 1
            else:
                nur_ast += 1
            abweichungen.append([label, pid, b.get("repo_url") or t.get("repo_url"),
                                 bv, tv, "echte Abweichung"])

        print()
        print("==", label, "==")
        print("  beide True            ", beide_ja)
        print("  beide False           ", beide_nein)
        print("  nur Baseline True     ", nur_base)
        print("  nur AST True          ", nur_ast)
        print("  eine Seite ohne Daten ", halbe)
        print("  beide ohne Daten      ", keine)

    return abweichungen


def zusatzinfo(ast_rows):
    print()
    print("== was die Baseline nicht ausdruecken kann ==")

    text_ja = [p for p in ast_rows if as_bool(ast_rows[p].get("cmake_tests_found"))]
    echt_ja = [p for p in ast_rows if as_bool(ast_rows[p].get("cmake_tests_reachable"))]
    anders = sorted(set(text_ja) - set(echt_ja), key=str)

    print("  Repos mit geschriebenem Testkommando   ", len(text_ja))
    print("  Repos mit ausgewertetem Testkommando   ", len(echt_ja))
    print("  anders entschieden als rein textuell   ", len(anders), anders)

    stellen = sum(as_int(ast_rows[p].get("cmake_test_sites")) for p in ast_rows)
    ok = sum(as_int(ast_rows[p].get("cmake_sites_invoked")) for p in ast_rows)
    unerr = sum(as_int(ast_rows[p].get("cmake_sites_file_unreachable")) for p in ast_rows)
    tot = sum(as_int(ast_rows[p].get("cmake_sites_wrapper_uncalled")) for p in ast_rows)
    print()
    print("  Fundstellen gesamt                     ", stellen)
    print("    ausgewertet                          ", ok)
    print("    verworfen, Datei nicht erreichbar    ", unerr)
    print("    verworfen, Wrapper nie aufgerufen    ", tot)

    betroffen = [p for p in ast_rows
                 if as_int(ast_rows[p].get("cmake_sites_file_unreachable"))
                 or as_int(ast_rows[p].get("cmake_sites_wrapper_uncalled"))]
    print("  Repos in denen etwas verworfen wurde   ", len(betroffen))

    # Wrapper die Tests registrieren aber nie aufgerufen werden
    mit_toten = [p for p in ast_rows
                 if (ast_rows[p].get("cmake_unused_test_wrappers") or "[]") != "[]"]
    print("  Repos mit nie aufgerufenem Wrapper     ", len(mit_toten), sorted(mit_toten, key=str))


def main():
    if len(sys.argv) < 3:
        print("python compare_deep.py baseline.csv ast.csv [abweichungen.csv]")
        return
    baseline = load(sys.argv[1])
    ast_rows = load(sys.argv[2])

    abweichungen = run(baseline, ast_rows, INDICATORS)
    zusatzinfo(ast_rows)

    print()
    print("Abweichungs- und Datenluecken-Zeilen gesamt:", len(abweichungen))

    if len(sys.argv) > 3:
        with open(sys.argv[3], "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["indicator", "project_id", "repo_url",
                        "baseline", "ast", "grund"])
            for z in abweichungen:
                w.writerow(z)
        print("->", sys.argv[3])


if __name__ == "__main__":
    main()
