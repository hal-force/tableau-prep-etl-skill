# TabPy Python interpreter dependencies

The Tableau Prep CLI runs Python script nodes via TabPy, which uses
*its own* Python interpreter — NOT the project `.venv`. If a script
imports a library and falls back silently when missing, the CLI run
will silently produce different numbers than the standalone harness.

This bit us once: rapidfuzz wasn't installed in TabPy's interpreter,
which made FUZZ_OK=False in the in-flow eval, which turned every
fuzzy-match into a strict case-sensitive equality test, which made
"State Police, Arkansas" vs "ARKANSAS STATE POLICE" score 0.0
instead of 1.0. Lift was 0.621 → 0.827 once installed.

## Required modules in TabPy's interpreter

Install with TabPy's pip, not `.venv`'s pip:

```sh
/Library/Frameworks/Python.framework/Versions/3.13/bin/pip install \
  rapidfuzz pandas PyPDF2 pdfplumber pdf2image pytesseract \
  python-dateutil openai
```

To audit:
```sh
/Library/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python -c "
for m in ('rapidfuzz','dateutil','pdfplumber','pdf2image','pytesseract','pandas','PyPDF2','openai'):
    try: __import__(m); print(f'{m}: ok')
    except ImportError as e: print(f'{m}: MISSING ({e})')"
```

## Restart TabPy after any install

TabPy caches modules in its sys.modules; new installs don't take
effect until the daemon restarts.
