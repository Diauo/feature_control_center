"""Process execution boundary reserved for Phase C.

The web process must not start feature scripts directly.  Phase C will place the
Supervisor, process-group termination, and log event ingestion behind this package.
"""
