"""Reproduce Superset's model-import context requirement without its full image."""
import builtins
import contextlib
import os
import runpy
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

SCRIPT = Path(__file__).parents[1] / 'docker/superset/initialize.py'


def run_initializer(path):
    active = False
    imports = []

    @contextlib.contextmanager
    def app_context():
        nonlocal active
        active = True
        try:
            yield
        finally:
            active = False

    superset = ModuleType('superset')
    superset.db = MagicMock()
    superset.db.session.query.return_value.filter_by.return_value.one_or_none.return_value = None
    superset.security_manager = MagicMock()
    superset.security_manager.find_user.return_value = None
    app_module = ModuleType('superset.app')
    app_module.create_app = lambda: type('App', (), {'app_context': staticmethod(app_context)})()
    model_module = ModuleType('superset.models.core')
    model_module.Database = MagicMock()
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == 'superset.models.core':
            if not active:
                raise RuntimeError('Working outside of application context.')
            imports.append(name)
        return real_import(name, *args, **kwargs)

    modules = {'superset': superset, 'superset.app': app_module,
               'superset.models.core': model_module}
    env = {'SUPERSET_ADMIN_USER': 'admin', 'SUPERSET_ADMIN_PASSWORD': 'EXAMPLE_ONLY',
           'POSTGRES_USER': 'formation', 'POSTGRES_PASSWORD': 'EXAMPLE_ONLY',
           'POSTGRES_DB': 'formation'}
    with patch.dict(sys.modules, modules), patch.dict(os.environ, env), \
            patch('builtins.__import__', guarded_import), patch('subprocess.run') as command:
        runpy.run_path(str(path), run_name='__main__')
    assert imports == ['superset.models.core']
    assert command.call_args_list[0].args[0] == ['superset', 'db', 'upgrade']
    assert command.call_args_list[-1].args[0] == ['superset', 'init']
    assert model_module.Database.call_count == 3
    superset.db.session.commit.assert_called_once()


def test_initialization_imports_models_with_an_active_context():
    run_initializer(SCRIPT)
