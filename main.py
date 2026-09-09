import sys

if __name__ == "__main__":
    if "--self-test" in sys.argv:
        import json
        import traceback
        from pathlib import Path
        report = Path(sys.argv[sys.argv.index("--self-test") + 1])
        try:
            from cardforge.self_test import run
            result = run()
            report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        except Exception:
            report.write_text(json.dumps({"passed": False, "error": traceback.format_exc()}), encoding="utf-8")
            sys.exit(1)
    else:
        from cardforge.gui import main
        main()
