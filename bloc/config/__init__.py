"""
Configuration: schema, validation, versioning, migration.

Read with the standard-library `tomllib` (Python 3.11+); written with `tomli_w`,
since there is no standard-library TOML writer.

Config carries an explicit version so that a schema change can migrate an
existing ~/bloc/config/bloc.config rather than silently falling back to
defaults. Validation happens at load, so a bad value fails loudly at boot
instead of surfacing as odd behaviour later.

Planned modules:

    schema.py   dataclasses, defaults, validation, version
    loader.py   load / deep-merge / atomic write / migrate
"""
