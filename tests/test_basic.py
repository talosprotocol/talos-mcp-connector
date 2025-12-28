def test_connector_import():
    try:
        import connector
        assert True
    except ImportError:
        # If connector is in root, we might need path setup
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
        import connector
        assert True
