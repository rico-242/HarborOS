set -eu
directory=/DATA/harbor/release/artifacts
install -m 644 /tmp/harbour-0.4.0-update.bundle "$directory/harbour-0.4.0-amd64.harbour-update"
install -m 644 /tmp/harbour-0.4.0-update.sha256 "$directory/harbour-0.4.0-amd64.harbour-update.sha256"
install -m 644 /tmp/harbor-source.tar.gz "$directory/harbour-0.4.0-source.tar.gz"
install -m 644 /tmp/harbour-0.4.0-source.sha256 "$directory/harbour-0.4.0-source.tar.gz.sha256"
cd "$directory"
sha256sum -c harbour-0.4.0-amd64.harbour-update.sha256
sha256sum -c harbour-0.4.0-source.tar.gz.sha256
rm -f /tmp/harbour-bad-release-test.bundle
