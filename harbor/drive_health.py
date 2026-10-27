"""Advisory SMART health; never changes disk eligibility or RAID topology."""
import json
import threading
import time


class Assessment(list):
    def __init__(self, unknown, warnings):
        super().__init__(unknown)
        self.warnings = warnings


def assessment(report):
    reasons = []
    if not isinstance(report, dict):
        report = {}
    if report.get('smart_status', {}).get('passed') is False:
        reasons.append('SMART overall health failed')
    labels = {5: 'reallocated sectors', 187: 'reported uncorrectable errors',
              197: 'pending sectors', 198: 'offline uncorrectable sectors'}
    for attribute in report.get('ata_smart_attributes', {}).get('table', []):
        value = attribute.get('raw', {}).get('value', 0)
        if attribute.get('id') in labels and isinstance(value, (int, float)) and value > 0:
            reasons.append(str(value) + ' ' + labels[attribute['id']])
    nvme = report.get('nvme_smart_health_information_log', {})
    if nvme.get('critical_warning'):
        reasons.append('NVMe critical health warning')
    if nvme.get('media_errors', 0):
        reasons.append(str(nvme['media_errors']) + ' NVMe media errors')
    if isinstance(nvme.get('percentage_used'), (int, float)) and nvme['percentage_used'] >= 100:
        reasons.append('NVMe rated endurance exhausted')
    return {'health': 'failing' if reasons else 'healthy' if 'smart_status' in report else 'unknown',
            'health_reasons': reasons, 'health_checked_at': int(time.time())}


class DriveHealth:
    def init_health(self):
        self._health_cache = {}
        self._health_lock = threading.Lock()
        self._health_refreshing = False
        self._health_refresh_at = 0

    def health(self, disks):
        from storage import identity
        unknown, warnings = [], []
        for disk in disks:
            try:
                result = self.run('smartctl', '-H', '-A', '-j', disk['id'], timeout=20, check=False)
                status = assessment(json.loads(result.stdout))
            except Exception:
                status = assessment({})
            with self._health_lock:
                self._health_cache[disk['id']] = dict(status, identity=identity(disk),
                    disk=disk['id'], serial=disk.get('serial') or disk['id'])
            disk.update(status)
            if status['health'] == 'unknown':
                unknown.append(disk['id'])
            if status['health'] == 'failing':
                warnings.append(dict(disk=disk['id'], serial=disk.get('serial') or disk['id'],
                                     reasons=status['health_reasons']))
        return Assessment(unknown, warnings)

    def cached_health(self, disks):
        from storage import identity
        with self._health_lock:
            for disk in disks:
                cached = self._health_cache.get(disk['id'], {})
                if cached.get('identity') == identity(disk):
                    disk.update({k: cached[k] for k in ('health', 'health_reasons', 'health_checked_at')})
                else:
                    disk.update(health='checking', health_reasons=[])
        self.refresh_health(disks)
        return disks

    def refresh_health(self, disks=None):
        with self._health_lock:
            if self._health_refreshing or time.monotonic() < self._health_refresh_at:
                return
            self._health_refreshing = True
        def worker():
            try:
                current = disks if disks is not None else self.inventory()
                self.health(current)
                present = {d['id'] for d in current}
                with self._health_lock:
                    self._health_cache = {k: v for k, v in self._health_cache.items() if k in present}
            except Exception:
                pass  # Inventory may change during hot-plug; retry on the next refresh.
            finally:
                with self._health_lock:
                    self._health_refresh_at = time.monotonic() + 60
                    self._health_refreshing = False
        threading.Thread(target=worker, name='drive-health', daemon=True).start()

    def pool_health(self):
        self.refresh_health()
        members = set(self.app.config.get('storage', {}).get('disks', []))
        with self._health_lock:
            failing = [dict(disk=k, serial=v['serial'], reasons=v['health_reasons'])
                       for k, v in self._health_cache.items() if k in members and v['health'] == 'failing']
        return {'health_risk': bool(failing), 'failing_drives': failing}
