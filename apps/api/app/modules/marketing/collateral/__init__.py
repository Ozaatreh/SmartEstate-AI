"""Brochure and poster generator (Phase 7C).

Every figure comes from the database at generation time through :mod:`.facts`; :mod:`.verify` re-reads the
rendered page and refuses to export if it shows a number that isn't one of those facts. No AI is involved.
"""
