from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
Path('/tmp/harbour-bad-release-test.bundle').unlink(missing_ok=True)
print('Disposable unhealthy update fixture removed from the VM.')
