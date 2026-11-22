import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch


def load_studio(modules):
    """Load a fresh extension package with a test queue and output directory."""
    source = Path(__file__).resolve().parents[1] / "custom_nodes/imagemagic_studio/__init__.py"
    spec = importlib.util.spec_from_file_location("test_imagemagic_extension", source)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {**modules, spec.name: module}):
        spec.loader.exec_module(module)
    return vars(module)
