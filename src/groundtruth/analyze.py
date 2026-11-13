# analyze.py
# Aufruf:  python analyze.py sites.jsonl

import collections, json, sys


def load(path):
    repos = []
    for line in open(path, encoding="utf-8"):
        if line.strip():
            repos.append(json.loads(line))
    return repos


def top(counter, n=10):
    for wert, anzahl in counter.most_common(n):
        print("   ", str(anzahl).rjust(5), wert)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "sites.jsonl"
    repos = load(path)
    sites = [s for r in repos for s in r["sites"]]
    ok = [s for s in sites if s["verdict"] == "invoked"]

    print("Repos in der Datei:", len(repos))
    print("Fundstellen:       ", len(sites))
    print()

    # --- Urteile ---
    print("Urteile:")
    top(collections.Counter(s["verdict"] for s in sites))
    print()

    # --- wer hat die meisten ---
    print("Repos mit den meisten Fundstellen:")
    top(collections.Counter({r["repo"]: len(r["sites"]) for r in repos}), 10)
    print()

    # --- add_test oder gtest_discover_tests ---
    print("Kommandoart (nur ausgewertete):")
    top(collections.Counter(s["command"] for s in ok))
    print()

    # --- Bedingungen ---
    mit_bed = [s for s in ok if s["guard"]]
    print("Unter einer Bedingung:", len(mit_bed), "von", len(ok))
    print("Haeufigste Bedingungen:")
    top(collections.Counter(s["guard"] for s in mit_bed), 10)
    print()

    # Wie viele Bedingungen sind verschachtelt, also mit AND verknuepft?
    verschachtelt = [s for s in mit_bed if " AND " in s["guard"]]
    print("davon verschachtelt (mehr als eine Bedingung):", len(verschachtelt))
    tiefste = max((s["guard"].count(" AND ") + 1 for s in mit_bed), default=0)
    print("tiefste Verschachtelung:", tiefste, "Bedingungen")
    print()

    # --- Schleifen ---
    print("Schleifentiefe (nur ausgewertete):")
    tiefen = collections.Counter(s["loop_depth"] for s in ok)
    for t in sorted(tiefen):
        print("   ", str(tiefen[t]).rjust(5), "mit Tiefe", t)
    print()

    # --- Wrapper ---
    in_wrapper = [s for s in ok if s["wrapper"]]
    print("In einem Wrapper:", len(in_wrapper), "- direkt:", len(ok) - len(in_wrapper))
    print("Haeufigste Wrappernamen:")
    top(collections.Counter(s["wrapper"] for s in in_wrapper), 10)
    print()

    tote = [w for r in repos for w in r["uncalled_wrappers"]]
    print("Wrapper die Tests registrieren und nie aufgerufen werden:", len(tote))
    print("   ", sorted(tote)[:12], "...")
    print()

    # --- Dateien ---
    print("Haeufigste Dateinamen mit Fundstelle:")
    top(collections.Counter(s["file"].split("/")[-1] for s in sites), 8)
    print()

    # --- die verworfenen nochmal genauer ---
    weg = [s for s in sites if s["verdict"] != "invoked"]
    print("Verworfene Fundstellen:", len(weg), "in",
          len(set(s["file"].split("/")[1] for s in weg)), "Repos")
    for s in weg[:15]:
        print("   ", s["verdict"].ljust(17), s["file"] + ":" + str(s["line"]))
    if len(weg) > 15:
        print("    ...", len(weg) - 15, "weitere")
    print()

    # --- Repos ohne jede ausgewertete Fundstelle, die aber welche geschrieben haben ---
    print("Repos mit Testkommando aber keinem ausgewerteten:")
    for r in repos:
        if r["sites"] and not [s for s in r["sites"] if s["verdict"] == "invoked"]:
            print("   ", r["repo"], "-", len(r["sites"]), "Fundstellen, alle verworfen")

    # Erreichbarkeit insgesamt, nur so als Hausnummer
    gesamt = sum(r["files"] for r in repos)
    err = sum(r["reachable"] for r in repos)
    vorlagen = sum(r["templates"] for r in repos)
    print()
    print("CMake-Dateien gesamt:", gesamt, "- davon Vorlagen:", vorlagen)
    print("erreichbar:", err, "von", gesamt - vorlagen,
          "=", str(round(100 * err / (gesamt - vorlagen))) + "%")
    print("Dateien mit Syntaxfehler:", sum(r["error_files"] for r in repos))

    # print([r["repo"] for r in repos if r["degraded"]])   # Repos ohne Wurzel

if __name__ == "__main__":
    main()
