# -*- coding: utf-8 -*-
"""python -m selftest 入口（与 python selftest.py 等价）。"""
from __future__ import annotations

from .runner import main

if __name__ == "__main__":
    raise SystemExit(main())
