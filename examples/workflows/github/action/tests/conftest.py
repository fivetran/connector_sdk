import sys
from pathlib import Path

# deploy_connector.py lives in ../scripts (it's the module action.yml actually
# invokes), not here -- put it on sys.path so test_deploy_connector.py can
# `import deploy_connector` without scripts/ needing to be a package itself.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
