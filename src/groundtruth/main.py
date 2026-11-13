# main.py
# CMake-Testanalyse
#
# Aufruf:  python main.py bar/            -> alle Repos unter bar/
#          python main.py bar/ 7958       -> nur eins, mit Details
#
# TODO: refactoring

import csv, os, sys, json
from tree_sitter import Language, Parser, Query, QueryCursor
import tree_sitter_cmake

LANG = Language(tree_sitter_cmake.language())
PARSER = Parser(LANG)

TESTCMDS = ["add_test", "gtest_discover_tests"]

SKIP_DIRS = [".git", ".hg", ".svn", ".venv", "__pycache__", "build",
             "cmake-build-debug", "cmake-build-release", "dist",
             "node_modules", "out", "target", "venv"]

# Dateien die ctest/cpack von selbst einliest, ohne dass sie jemand include()t
AUTO_LOADED = ["ctestconfig.cmake", "cpackconfig.cmake", "ctestcustom.cmake"]

# Schluesselwoerter die in project(...) nach LANGUAGES kommen.
CONTROL_WORDS = ["ANDROID", "ARCHIVE_OUTPUT_DIRECTORY", "BINARY_DIR", "COMPAT_VERSION",
                 "CXX_EXTENSIONS", "DESCRIPTION", "EXPORT_NAME", "HOMEPAGE_URL",
                 "IMPORTED", "LANGUAGES", "LINKER_LANGUAGE", "NAME",
                 "NO_SYSTEM_FROM_IMPORTED", "PROJECT_NAME", "VERSION",
                 "VERSION_MAJOR", "VERSION_MINOR", "VERSION_PATCH", "VERSION_TWEAK"]

LANG_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_+-#.")

# Queries. Die muss man einmal kompilieren, sonst wird es extrem langsam.
Q_CMD = Query(LANG, """
(normal_command
  (identifier) @name
  (argument_list (argument)* @arg)?)
""")
Q_DEF = Query(LANG, """
[
  (macro_def    (macro_command    (argument_list) @sig) (body) @body)
  (function_def (function_command (argument_list) @sig) (body) @body)
]
""")
Q_LOOP = Query(LANG, """
(foreach_loop (foreach_command (argument_list) @sig) (body) @body)
""")
Q_IF = Query(LANG, "(if_condition) @block")

DEBUG = False


def text_of(node, src):
    return src[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


# alle CMake-Dateien eines Repos einsammeln
def collect_files(root):
    out = []
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            lf = f.lower()
            if lf == "cmakelists.txt" or lf == "cmakelists.txt.in" \
               or lf.endswith(".cmake") or lf.endswith(".cmake.in"):
                out.append(os.path.join(current, f))
    return out


# Eine Datei parsen und alles rausholen was wir brauchen.
# Rueckgabe ist ein dict, das reicht erstmal.
def parse_file(path):
    result = {"path": path, "ok": False, "has_error": False, "errors": [],
              "cmds": [], "defs": [], "loops": [], "ifs": [], "toplevel": set(),
              # die flachen Flags die auch das Baseline-Skript bildet
              "tests_found": False, "gtests_found": False, "languages": [],
              "uses_gtest": False, "uses_catch2": False, "enable_testing": False}
    try:
        with open(path, "rb") as fh:
            src = fh.read()
    except OSError as e:
        result["errors"].append(str(e))
        return result

    tree = PARSER.parse(src)
    result["ok"] = True
    result["has_error"] = tree.root_node.has_error

    # --- Kommandos ---
    # ein Kommando ist (name, [args], zeile, offset)
    cursor = QueryCursor(Q_CMD)
    for _, caps in cursor.matches(tree.root_node):
        names = caps.get("name", [])
        if not names:
            continue
        n = names[0]
        args = [text_of(a, src) for a in caps.get("arg", [])]
        result["cmds"].append((text_of(n, src), args, n.start_point[0] + 1, n.start_byte))
    result["cmds"].sort(key=lambda c: c[3])

    # --- flache Flags, genau wie das Baseline-Skript sie bildet ---
    for (name, args, line, offset) in result["cmds"]:
        n = name.lower()
        if n in TESTCMDS:
            result["tests_found"] = True
        if n == "gtest_discover_tests":
            result["gtests_found"] = True
        if n == "enable_testing":
            result["enable_testing"] = True
        if n == "find_package" and args:
            paket = args[0].lower()
            if paket == "gtest" or paket == "googletest":
                result["uses_gtest"] = True
            if paket == "catch2":
                result["uses_catch2"] = True
        if n == "project":
            result["languages"] += project_languages(args)

    # --- Makro- und Funktionsdefinitionen ---
    # (name, start, end, set_der_aufgerufenen_kommandos)
    cursor = QueryCursor(Q_DEF)
    for _, caps in cursor.matches(tree.root_node):
        sigs = caps.get("sig", [])
        bodies = caps.get("body", [])
        if not sigs or not bodies:
            continue
        sig = sigs[0]
        if not sig.named_children:
            continue
        body = bodies[0]
        # erstes Argument ist der Name, der Rest sind die Parameter die uns egal sind
        name = text_of(sig.named_children[0], src)
        # welche Kommandos ruft der Rumpf auf
        called = set()
        inner = QueryCursor(Q_CMD)
        for _, cc in inner.matches(body):
            nn = cc.get("name", [])
            if nn:
                called.add(text_of(nn[0], src).lower())
        result["defs"].append((name, body.start_byte, body.end_byte, called))

    # --- foreach-Schleifen, nur die Ausdehnung ---
    cursor = QueryCursor(Q_LOOP)
    for _, caps in cursor.matches(tree.root_node):
        bodies = caps.get("body", [])
        if bodies:
            result["loops"].append((bodies[0].start_byte, bodies[0].end_byte))

    # --- if-Zweige ---
    # Die Grammatik legt alle Zweige als Geschwister unter eine if_condition,
    # also: if_command, body, elseif_command, body, else_command, body, endif.
    # Man muss jeden body mit dem Kommando davor zusammenbringen.
    cursor = QueryCursor(Q_IF)
    for _, caps in cursor.matches(tree.root_node):
        for block in caps.get("block", []):
            condition = ""
            for child in block.children:
                if child.type in ("if_command", "elseif_command"):
                    args = []
                    for sub in child.children:
                        if sub.type == "argument_list":
                            args = list(sub.named_children)
                    condition = " ".join(text_of(a, src) for a in args)
                elif child.type == "else_command":
                    condition = "else"
                elif child.type == "body":
                    result["ifs"].append((condition, child.start_byte, child.end_byte))

    # --- Kommandos auf oberster Ebene, also ausserhalb jeder Definition ---
    spans = [(d[1], d[2]) for d in result["defs"]]
    for (name, args, line, offset) in result["cmds"]:
        inside = False
        for (start, end) in spans:
            if start <= offset < end:
                inside = True
                break
        if not inside:
            result["toplevel"].add(name.lower())

    return result


def looks_like_language(text):
    t = text.strip()
    if not t or t.upper() in CONTROL_WORDS:
        return False
    return all(c in LANG_CHARS for c in t)


# project(Foo LANGUAGES CXX C) -> ["CXX", "C"]
def project_languages(args):
    out = []
    i = 0
    while i < len(args):
        if args[i].upper() == "LANGUAGES":
            i += 1
            while i < len(args):
                if args[i].upper() in CONTROL_WORDS:
                    break
                if looks_like_language(args[i]):
                    out.append(args[i])
                i += 1
            continue
        i += 1
    return out


def is_template(path):
    return path.endswith(".in")


def norm(*parts):
    return os.path.normpath(os.path.join(*parts))


# Breitensuche ab der CMakeLists.txt im Wurzelverzeichnis.
def reachability(analyses, repo_root):
    by_path = {}
    for a in analyses:
        by_path[a["path"]] = a

    templates = set(p for p in by_path if is_template(p))
    candidates = set(p for p in by_path if p not in templates)

    root = norm(repo_root, "CMakeLists.txt")
    if root not in candidates:
        # Repo ohne eine einzige Wurzel, z.B. mehrere unabhaengige Teilprojekte.
        # Dann lieber alles als erreichbar behandeln als willkuerlich eine Datei
        # zur Wurzel erklaeren und den Rest wegzuwerfen.
        return candidates, templates, 0, True

    # Index nach Dateiname fuer include(name) ohne Pfad.
    # sorted() ist wichtig, sonst ist die Reihenfolge je Lauf anders und das
    # Ergebnis nicht reproduzierbar.
    by_name = {}
    for p in sorted(candidates):
        key = os.path.basename(p).lower()
        by_name.setdefault(key, []).append(p)

    reachable = set([root])
    queue = [root]
    unresolved = 0

    for name in AUTO_LOADED:
        for p in by_name.get(name, []):
            if p not in reachable:
                reachable.add(p)
                queue.append(p)

    while queue:
        current = queue.pop()
        a = by_path.get(current)
        if a is None:
            continue
        directory = os.path.dirname(current)

        targets = []

        # Bei kaputten Dateien schluckt die Fehlerbehandlung ganze Bloecke,
        # dann fehlen uns Kommandos. Also nicht wegschneiden, sondern alle
        # direkten Unterverzeichnisse als erreichbar annehmen.
        if a["has_error"]:
            for p in subdirectory_lists(directory, candidates):
                targets.append((p, True))

        for (name, args, line, offset) in a["cmds"]:
            n = name.lower()
            if not args:
                continue
            arg = args[0].strip('"')

            if n == "include":
                hits = resolve_include(arg, directory, candidates, by_name)
                if hits:
                    for h in hits:
                        targets.append((h, True))
                else:
                    targets.append((None, False))

            elif n == "add_subdirectory":
                if "${" in arg:
                    # Variabler Unterverzeichnisname, z.B. add_subdirectory(${SUBDIR}).
                    # Welches gemeint ist weiss man statisch nicht. Genau eine Ebene
                    # tief aufmachen - alles aufzumachen wuerde bei einer einzigen
                    # solchen Zeile im Wurzelverzeichnis das ganze Repo inkl. aller
                    # mitgelieferten Fremdbibliotheken als erreichbar markieren.
                    for p in subdirectory_lists(directory, candidates):
                        targets.append((p, True))
                    targets.append((None, False))
                else:
                    candidate = norm(directory, arg, "CMakeLists.txt")
                    if candidate in candidates:
                        targets.append((candidate, True))
                    else:
                        targets.append((None, False))

            elif n == "find_package":
                # find_package(X) kann ein mitgeliefertes FindX.cmake laden.
                # Wenn es keins gibt ist das normal (Paket liegt woanders),
                # also hier nie als unaufloesbar zaehlen.
                for p in by_name.get("find" + arg.lower() + ".cmake", []):
                    targets.append((p, True))

        for (target, resolved) in targets:
            if not resolved:
                unresolved += 1
                continue
            if target not in reachable:
                reachable.add(target)
                queue.append(target)

    return reachable, templates, unresolved, False


def subdirectory_lists(directory, candidates):
    out = []
    for p in candidates:
        parent = os.path.dirname(p)
        if os.path.basename(p).lower() == "cmakelists.txt" \
           and os.path.dirname(parent) == directory and parent != directory:
            out.append(p)
    return out


def resolve_include(arg, directory, candidates, by_name):
    name = os.path.basename(arg)
    if "${" in name:
        return []
    if not name.lower().endswith(".cmake"):
        name = name + ".cmake"

    if "${" not in arg:
        candidate = norm(directory, arg)
        if candidate in candidates:
            return [candidate]
        if not arg.lower().endswith(".cmake"):
            candidate = norm(directory, arg + ".cmake")
            if candidate in candidates:
                return [candidate]

    matches = by_name.get(name.lower(), [])
    if len(matches) <= 1:
        return list(matches)
    # Mehrdeutig - welche Datei CMake nimmt haengt an CMAKE_MODULE_PATH und das
    # wissen wir nicht. Also alle nehmen statt irgendeine. Vorher in der Naehe
    # suchen, das trifft es meistens.
    nearby = [p for p in matches if p.startswith(directory + os.sep)]
    if nearby:
        return nearby
    return list(matches)


# Welche Makros/Funktionen registrieren einen Test, und welche werden aufgerufen?
# Zwei Fixpunktiterationen. Muss ueber alle Dateien laufen, weil die Helfer
# meistens in cmake/*.cmake stehen und aus den Unterverzeichnissen gerufen werden.
def find_wrappers(analyses, reachable):
    bodies = {}   # name -> menge der kommandos die der rumpf aufruft
    for a in analyses:
        if a["path"] not in reachable:
            continue
        for (name, start, end, called) in a["defs"]:
            key = name.lower()
            if key not in bodies:
                bodies[key] = set()
            bodies[key] |= called

    # 1. Durchlauf: wer registriert einen Test?
    registers = set()
    for key in bodies:
        for t in TESTCMDS:
            if t in bodies[key]:
                registers.add(key)
    while True:
        grown = set()
        for key in bodies:
            if key in registers:
                continue
            if bodies[key] & registers:
                grown.add(key)
        if not grown:
            break
        registers |= grown

    # 2. Durchlauf: wer wird ueberhaupt aufgerufen?
    called_names = set()
    for a in analyses:
        if a["path"] in reachable:
            called_names |= a["toplevel"]
    while True:
        grown = set()
        for key in list(called_names):
            if key in bodies:
                grown |= (bodies[key] - called_names)
        if not grown:
            break
        called_names |= grown

    used = sorted(registers & called_names)
    uncalled = sorted(registers - called_names)
    return used, uncalled


# Urteil pro Fundstelle festlegen
def collect_sites(analyses, reachable, uncalled_wrappers):
    uncalled = set(w.lower() for w in uncalled_wrappers)
    out = []
    for a in sorted(analyses, key=lambda x: x["path"]):
        file_reachable = a["path"] in reachable
        for (name, args, line, offset) in a["cmds"]:
            if name.lower() not in TESTCMDS:
                continue

            # in welchem Wrapper steckt das? Bei Verschachtelung der engste.
            wrapper = None
            width = None
            for (dname, start, end, called) in a["defs"]:
                if start <= offset < end:
                    if width is None or (end - start) < width:
                        wrapper = dname
                        width = end - start

            if not file_reachable:
                verdict = "file_unreachable"
            elif wrapper is not None and wrapper.lower() in uncalled:
                verdict = "wrapper_uncalled"
            else:
                verdict = "invoked"

            # if-Bedingungen, aussen zuerst. Der breiteste Block ist der aeussere.
            enclosing = []
            for (condition, start, end) in a["ifs"]:
                if start <= offset < end:
                    enclosing.append((end - start, condition))
            enclosing.sort(reverse=True)
            conditions = [c for (_, c) in enclosing if c]
            if conditions:
                guard = " AND ".join(conditions)
            else:
                guard = None

            # Schleifentiefe
            depth = 0
            for (start, end) in a["loops"]:
                if start <= offset < end:
                    depth += 1

            out.append({"file": a["path"], "line": line, "command": name.lower(),
                        "verdict": verdict, "wrapper": wrapper,
                        "guard": guard, "loop_depth": depth})
    return out


def analyse_repo(repo_root):
    files = collect_files(repo_root)
    analyses = [parse_file(p) for p in files]
    reachable, templates, unresolved, degraded = reachability(analyses, repo_root)
    used, uncalled = find_wrappers(analyses, reachable)
    sites = collect_sites(analyses, reachable, uncalled)

    if DEBUG:
        print("  files:", len(files), "reachable:", len(reachable),
              "templates:", len(templates), "unresolved:", unresolved)

    # Die flachen Flags gucken absichtlich auf alle Dateien, auch die nicht
    # erreichbaren, genau wie die Baseline.
    flach = {}
    for k in ("tests_found", "gtests_found", "uses_gtest", "uses_catch2", "enable_testing"):
        flach[k] = any(a[k] for a in analyses)

    sprachen = []
    for a in analyses:
        for l in a["languages"]:
            if l not in sprachen:
                sprachen.append(l)
    sprachen.sort()

    return {"files": len(files), "reachable": len(reachable),
            "templates": len(templates), "unresolved": unresolved,
            "degraded": degraded, "languages": sprachen,
            "error_files": sum(1 for a in analyses if a["has_error"]),
            "read_errors": [e for a in analyses for e in a["errors"]],
            "has_cmakelists": any(a["ok"] for a in analyses),
            "tests_found": flach["tests_found"],
            "gtests_found": flach["gtests_found"],
            "uses_gtest": flach["uses_gtest"],
            "uses_catch2": flach["uses_catch2"],
            "enable_testing": flach["enable_testing"],
            "tests_reachable": any(s["verdict"] == "invoked" for s in sites),
            "wrappers": used, "uncalled_wrappers": uncalled, "sites": sites}


def main():
    if len(sys.argv) < 2:
        print("python main.py <clone-dir> [repo-id]")
        return
    base = sys.argv[1]

    if len(sys.argv) > 2:
        # Einzelnes Repo, mit allen Fundstellen auf der Konsole
        pid = sys.argv[2]
        r = analyse_repo(os.path.join(base, pid))
        print("Repo", pid)
        print("  CMake-Dateien", r["files"], "davon erreichbar", r["reachable"])
        print("  Wrapper benutzt:", r["wrappers"])
        print("  Wrapper nie aufgerufen:", r["uncalled_wrappers"])
        for s in r["sites"]:
            print("   ", s["verdict"].ljust(17), s["file"] + ":" + str(s["line"]),
                  "wrapper=" + str(s["wrapper"]),
                  "if=" + str(s["guard"]),
                  "loop=" + str(s["loop_depth"]))
        return

    # Alle Repos unter base.
    # Gleich beim Durchlaufen rausschreiben, eine Zeile JSON je Repo.
    # -> Trotzdem Daten wenn ein Lauf abgebrochen wird
    SPALTEN = ["project_id", "has_cmakelists", "cmake_tests_found",
               "cmake_gtests_found", "cmake_uses_gtest", "cmake_uses_catch2",
               "cmake_enable_testing", "cmake_files_found", "cmake_files_reachable",
               "cmake_files_unreachable", "cmake_files_templates",
               "cmake_files_with_syntax_errors", "cmake_unresolved_directives",
               "cmake_tests_reachable", "cmake_tests_via_wrapper",
               "cmake_test_sites", "cmake_sites_invoked",
               "cmake_sites_file_unreachable", "cmake_sites_wrapper_uncalled",
               "cmake_sites_in_wrapper", "cmake_sites_guarded",
               "cmake_site_guards_distinct", "cmake_sites_in_loop",
               "cmake_sites_max_loop_depth",
               "cmake_test_wrappers", "cmake_unused_test_wrappers",
               "cmake_languages"]

    results = {}
    ids = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
    with open("sites.jsonl", "w") as jl, open("out.csv", "w", newline="") as cf:
        w = csv.writer(cf)
        w.writerow(SPALTEN)
        for i, pid in enumerate(ids, 1):
            r = analyse_repo(os.path.join(base, pid))
            results[pid] = r

            record = dict(r)
            record["repo"] = pid
            jl.write(json.dumps(record) + "\n")

            ok = [s for s in r["sites"] if s["verdict"] == "invoked"]
            tiefen = [s["loop_depth"] for s in ok]
            w.writerow([pid, r["has_cmakelists"], r["tests_found"],
                        r["gtests_found"], r["uses_gtest"], r["uses_catch2"],
                        r["enable_testing"], r["files"], r["reachable"],
                        r["files"] - r["reachable"] - r["templates"],
                        r["templates"], r["error_files"], r["unresolved"],
                        r["tests_reachable"], len(r["wrappers"]) > 0,
                        len(r["sites"]), len(ok),
                        len([s for s in r["sites"] if s["verdict"] == "file_unreachable"]),
                        len([s for s in r["sites"] if s["verdict"] == "wrapper_uncalled"]),
                        len([s for s in ok if s["wrapper"]]),
                        len([s for s in ok if s["guard"]]),
                        len(set(s["guard"] for s in ok if s["guard"])),
                        len([s for s in ok if s["loop_depth"] > 0]),
                        max(tiefen) if tiefen else 0,
                        r["wrappers"], r["uncalled_wrappers"], r["languages"]])

            jl.flush()
            cf.flush()
            print(i, "/", len(ids), pid, len(r["sites"]), "Fundstellen")

    # Zusammenfassung
    all_sites = []
    for pid in results:
        all_sites += results[pid]["sites"]
    ok = [s for s in all_sites if s["verdict"] == "invoked"]
    print()
    print("Fundstellen gesamt       ", len(all_sites))
    print("  ausgewertet            ", len(ok))
    print("  Datei nicht erreichbar ", len([s for s in all_sites if s["verdict"] == "file_unreachable"]))
    print("  Wrapper nie aufgerufen ", len([s for s in all_sites if s["verdict"] == "wrapper_uncalled"]))
    print("  davon unter Bedingung  ", len([s for s in ok if s["guard"]]))
    print("  davon in Schleife      ", len([s for s in ok if s["loop_depth"] > 0]))
    print("Repos mit Testkommando   ", len([p for p in results if results[p]["sites"]]))
    print("Repos mit ausgewertetem  ",
          len([p for p in results
               if [s for s in results[p]["sites"] if s["verdict"] == "invoked"]]))

    print("-> sites.jsonl und out.csv")


if __name__ == "__main__":
    main()
