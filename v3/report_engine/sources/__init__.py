"""SQL row adapters -> typed facts.

Pure functions (no I/O, no Flask, no DB). The web layer fetches rows from the
Reporting API and hands them here. Builders consume only the facts these
produce, so report math stays separate from API row shapes.
"""
