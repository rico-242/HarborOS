# Green desktop update

Historical interface, superseded by [the dark desktop](DARK-DESKTOP.md) on October 25, 2026.

Harbor's interface now follows a desktop layout inspired by ZimaOS, retaining its own green identity and original assets.

## Desktop

- Green landscape background and translucent panels.
- Clock, CPU/RAM, storage, and connection widgets on the left.
- File and snapshot shortcuts above the app launcher grid.
- Floating dock for Home, Files, App Store, Storage, Sharing, Snapshots, and Settings.
- Search apps and tools with the top search field; press `/` to focus it.
- Drag application icons to rearrange them. Keyboard users can focus a launcher and press Alt + Left/Right.
- Widget settings control system, storage, and connection panels, with Forest, Moss, and Night green backgrounds.
- Layout, background, and widget preferences persist in the browser.

Installed applications appear on the desktop. Running apps open their web interface; stopped apps use the existing Start workflow. App Store category and text filters operate on the real catalog.

## Verification

- Browser checks passed for launcher search and Enter-to-open, Files navigation, App Store search/category filtering, widget preferences, and resetting the desktop.
- Mouse and keyboard rearranging were exercised in the local preview; the new order survived reload.
- The deployed NAS interface displayed real CPU/RAM values, the Btrfs mirror, shared folders, and drive advisories.
- Checked both the wide local preview and the compact live browser pane. The compact layout keeps the primary launchers above the dock.
- Existing eight HTTP integration tests passed; JavaScript syntax validation passed.
- Browser console reported no errors during live verification.

The deployment changes four static web assets. Prior UI versions are saved under `/var/lib/harbor/ui-backups`. Deployment hashes are recorded in `/var/lib/harbor/ui-deployment.json`. The standalone image is updated to contain the same assets.

All icons, CSS illustrations, and the vector landscape are original code assets. No ZimaOS logos, wallpaper files, or source assets were copied. Layout references: [official ZimaOS feature documentation](https://www.zimaspace.com/docs/zimaos/Features).
