"""nimby3d train model generator: a train spec (JSON) to the GOV2 models the nimby3d add-on draws.

  from trainmodel import validate, checked, generate, new_spec
  problems = validate(spec)                 # {"errors": [...], "warnings": [...]}, each {path, en, zh}
  out = generate(checked(spec), glb=False)  # {"files": {name: bytes}, "entry": manifest model entry, "stats": [...]}

Standard library only. spec.py: the spec's fields, checks and new specs; carbody.py / hood.py: the
two body styles; export.py: the files; gov.py: GOV2 (and the add-on's reader, ported); modcheck.py:
a mod folder judged as the add-on judges it; preview.py: the compact mesh for the editor's viewer.
"""
from __future__ import annotations

from .export import build_model, generate, gov_bytes, rig_bytes, glb_bytes, file_stem, plain_name, GENERATOR, GENERATOR_VERSION  # noqa: F401
from .gov import encode as gov_encode, decode as gov_decode, bake_stats, GovError  # noqa: F401
from .spec import validate, checked, normalized, new_spec, fit, arrange, SpecError  # noqa: F401
