"""Errors that mean "the input is unusable", as opposed to a bug: the CLI reports them as one line."""

from __future__ import annotations


class IngestError(ValueError):
    """A file that cannot be turned into a Document (bad XML, undecodable text, id collision, ...)."""
