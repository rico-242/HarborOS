set -eu
install -m 644 /tmp/harbour-0.3.0-source.tar.gz /DATA/harbor/release/artifacts/harbour-0.3.0-source.tar.gz
install -m 644 /tmp/harbour-0.3.0-source.tar.gz.sha256 /DATA/harbor/release/artifacts/harbour-0.3.0-source.tar.gz.sha256
cd /DATA/harbor/release/artifacts
sha256sum -c harbour-0.3.0-source.tar.gz.sha256
