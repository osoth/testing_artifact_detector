# compare.py
# Baseline (regex) gegen den eigenen AST-Detektor stellen.
# Beide CSVs sind pro Zeile ein Repo, Schluessel ist project_id.
#
#
# Aufruf:  python compare.py baseline.csv ast.csv [abweichungen.csv]
#
# TODO: Refactoring

import csv, sys

INDICATORS = [
    ("has_cmake_file",                               "has_cmakelists", ["has_cmakelists"]),
    ("uses_gtest (find_package)",                    "uses_gtest",     ["cmake_uses_gtest"]),
    ("uses_catch2 (find_package)",                   "uses_catch2",    ["cmake_uses_catch2"]),
    ("tests_found (add_test/gtest_discover_tests)",  "has_cpp_tests",  ["cmake_tests_found"]),
    ("gtests_found (gtest_discover_tests)",          "gtests_found",   ["cmake_gtests_found"]),
]


# Zellen sind Strings. "True"/"False" ist klar, aber leer heisst "keine Daten"
# und das ist NICHT dasselbe wie False - sonst zaehlt man fehlende Laeufe als
# Nein-Befund. Also drei Zustaende: True, False, None.
def as_bool(v):
    if v is None:
        return None
    t = str(v).strip().lower()
    if t == "" or t == "nan":
        return None
    return t == "true"


def load(path):
    rows = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pid = row.get("project_id") or row.get("joss_id") or ""
            if pid:
                rows[pid] = row
    return rows


# mehrere Spalten mit ODER, leere ignorieren
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
        print("  Repos gesamt          ", len(alle_ids))

    return abweichungen


def check_sprachen(baseline, ast_rows):
    if not any("has_cpp" in ast_rows[pid] for pid in ast_rows):
        print()
        print("== Kontrolle Spracherkennung ==")
        print("  AST-Seite hat keine Sprachspalten, nichts zu pruefen")
        return

    schief = 0
    for pid in baseline:
        if pid not in ast_rows:
            continue
        for c in ("has_cpp", "has_c"):
            if as_bool(baseline[pid].get(c)) != as_bool(ast_rows[pid].get(c)):
                schief += 1
    print()
    print("== Kontrolle Spracherkennung ==")
    print("  Unterschiede bei has_cpp/has_c:", schief, "(sollte 0 sein)")


def main():
    if len(sys.argv) < 3:
        print("python compare.py baseline.csv ast.csv [abweichungen.csv]")
        return
    baseline = load(sys.argv[1])
    ast_rows = load(sys.argv[2])

    abweichungen = run(baseline, ast_rows, INDICATORS)
    check_sprachen(baseline, ast_rows)

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


# nur ausfuehren wenn man das Skript startet, nicht beim Import.
# Ohne das laeuft beim "from main import parse_file" die ganze Analyse los.
if __name__ == "__main__":
    main()
