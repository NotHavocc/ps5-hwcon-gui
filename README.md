<h1 align="center">ps5-hwcon-gui</h1>

<p align="center">
  <img src="docs/about.png" alt="About tab" width="70%">
</p>

<p align="center">
  <img alt="GitHub Release" src="https://img.shields.io/github/v/release/NotHavocc/ps5-hwcon-gui">
  <img alt="Discord" src="https://img.shields.io/discord/1562764939486298175?logo=discord&label=PS5Linux%20Server">
  <img alt="Static" src="https://img.shields.io/badge/open_source-with_%3C3-blue">
</p>

<p align="center">
A desktop (PyQt6) port of <a href="https://github.com/NotHavocc/ps5-hwcon-plugin">ps5-hwcon-plugin</a> for
PS5 Linux. Control your PS5's hardware on Linux with ease.
</p>

---

## Requirements

- A PS5 running Linux with the [ps5-linux-patches](https://github.com/ps5-linux/ps5-linux-patches)
  kernel. The app only talks to the sysfs interfaces that kernel adds.
- Python 3.9+ and PyQt6.
- Root, because every control writes to sysfs. The window shows a warning banner when it isn't
  running as root or when kernel interfaces are missing.

## Install and run

Run this on the PS5 as your normal user (not root):

```sh
curl -fsSL https://raw.githubusercontent.com/NotHavocc/ps5-hwcon-gui/main/install.sh | bash
```

From a copy of this repo, `./install.sh` does the same without downloading anything.

Run the same command again to update. Your settings are kept. To uninstall:

```sh
curl -fsSL https://raw.githubusercontent.com/NotHavocc/ps5-hwcon-gui/main/install.sh | bash -s -- --uninstall
```

Once installed, open it from the app menu or a terminal:

```sh
ps5-hwcon-gui          # open the window
ps5-hwcon-gui --tray   # start hidden in the tray
```

The app needs root, so it asks for your password each time it opens. To skip that, add
`--passwordless` to the install command:

```sh
curl -fsSL https://raw.githubusercontent.com/NotHavocc/ps5-hwcon-gui/main/install.sh | bash -s -- --passwordless
```

This adds a sudoers rule for your user that only covers opening this app, and updates keep it. The
trade-off is that anything running as your user can then open the app as root without a password.
Run the installer with `--no-passwordless` to remove the rule.

Settings are stored in `/var/lib/ps5-hwcon/settings.json` when running as root, otherwise in
`~/.config/ps5-hwcon/`. Set `PS5HWCON_SETTINGS_DIR` to use another directory.

### Background protection and Restore on Startup

Thermal Guard, Overheat Alarm and LED loops run inside the app. Closing the window hides it to the
system tray and they keep running. Use **Quit** in the window or the tray menu to exit, which stops
them. Settings you applied stay in place until you reboot. The desktop's tray won't accept an icon
from root, so the icon is shown by a small helper process that runs as you and closes with the app.

To have all of this from the moment you log in, turn on **Start in Tray at Login** on the About page.
It adds `~/.config/autostart/ps5-hwcon-gui.desktop`, which runs `ps5-hwcon-gui --tray`. The app
needs root, so install with `--passwordless` or you'll be asked for your password at each login. It
needs a desktop with a system tray, and waits up to 15 s for the tray to appear after login.
Uninstalling removes the login item.

Restore on Startup re-applies saved settings when the app starts, each one as soon as its driver is
ready. If a driver is still loading, it keeps retrying for up to 60 s and logs which settings it is
waiting for, or gave up on.

Only one instance can run at a time, because two thermal guards would fight over the fan target.

## Features

The sidebar has Dashboard, Fan, CPU & GPU, Memory, Display, LED and About. Dashboard and CPU & GPU
each have a switch at the top for their two pages. Hover an option to see what it does.

### Dashboard

- **Now**: everything at a glance: every temperature sensor, CPU clock, governor and load with a bar per
  core, GPU clock, governor, busy % and VRAM use, fan speed and mode, and RAM and swap use.
- **History**: charts of temperatures, CPU and GPU clocks, CPU and GPU load, fan speed and memory use over the
  last 1, 5 or 10 minutes. Hover a chart to read the values at any moment.
- Sampled every 2 s, and kept while the window is hidden in the tray, so you can check what
  happened during a game.
- **Export CSV** saves the whole 10-minute history to a spreadsheet-friendly file.

### Fan

**Fan Control** switches between **Target Temperature** (the original control) and **Fan Curve**.
Fan curves need a kernel with the `ps5_fan` hwmon driver, which ps5-linux-patches includes from
7.2.3 ([#60](https://github.com/ps5-linux/ps5-linux-patches/pull/60)). The app and installer look
for that device rather than the kernel version, so any kernel carrying the driver works. Without it
the page opens on Target Temperature and Fan Curve is greyed out. Kernels with the driver drop
`target_temp`, so there a target is applied as a curve that reaches 45% at the target and full speed
6 °C above it.

- **Temperatures**: live CPU (`k10temp`), GPU, SSD and any other hwmon sensors, refreshed every 2 s
  and colored as they approach the overheat threshold.
- **Fan curve** (hwmon kernels): drag the 8 curve points (SoC temperature → fan speed) and the
  stop temperature, then **Apply Curve**. The editor keeps the curve valid for the driver:
  temperatures rise from point to point, speed never drops, and the last point is 100%. Above
  90 °C the kernel runs the fan at full speed no matter what.
- **Curve presets**: Quiet (the kernel default), Balanced, Cool, and Full Speed.
- **Target presets**: Quiet 85 °C, Default 80 °C, Balanced 72 °C, Cool 65 °C and
  Max Cooling 50 °C.
- **Manual Target**: any target from 40 to 90 °C.
- **Restore on Startup**: re-applies your last fan setting (curve, target, Full Speed or Console
  Firmware) once per boot, when the app first starts. Restarting the app later in the same boot
  leaves the fan alone, so changes made from the Decky plugin or a terminal stick.
- **Thermal Guard**: when the CPU reaches the Overheat Threshold (80–100 °C, default 95), the fan
  switches to Full Speed (or the Max Cooling target). Your setting comes back once the CPU is
  10 °C cooler.
- **Overheat Alarm**: plays the console's error beep once when the CPU reaches the threshold, and
  re-arms after it cools down.

### CPU

- **Governor**: every cpufreq governor the kernel offers, applied to all CPUs.
- **Status**: active governor (or **Mixed**), average and peak clock and hardware range. Hover the clock to see the driver.
- **Manual Clock**: locks every CPU to one clock (`scaling_min_freq` = `scaling_max_freq`). The
  slider snaps to `scaling_available_frequencies` when the driver lists them. **Automatic** restores
  the full range.
- **Boost to 3.5 GHz**: turns the CPU boost on or off through `/sys/devices/system/cpu/cpufreq/boost`.
  Shown only on kernels that have it (rmuxnet's kernel).
- **Restore on Startup**: re-applies your last governor, clock lock and boost.

### Console model

The app detects a PS5 Pro from its GPU PCI ID (`1002:13da` or `1002:13dc`). If no AMD GPU shows
up in sysfs, it checks dmesg for the Pro's Viola firmware instead. The model is shown under the
page list, and in the window title on a Pro. If detection is wrong, pick **PS5 Pro** or **PS5 /
Slim** under **Console Model** on the About page. The choice is saved as `console_model` in the
settings, and **Auto** goes back to detection. On a Pro, the GPU page puts the Pro settings first,
the Fan page shows the GPU temperature next to the CPU, the CPU page says the firmware sets the
CPU clocks, and the Memory page suggests 4 GB of VRAM if
games crash after long sessions.

### GPU

- **Governor**: the devfreq governors offered by `ps5-gpufreq` (Ondemand, Performance, Powersave,
  Userspace).
- **Status**: active governor, current and target clock, allowed range.
- **Manual Clock**: locks the GPU to one of `available_frequencies`. **Automatic** removes the
  limits.
- **Restore on Startup**: re-applies your last GPU governor and clock lock.
- **Thermal Limit**: the GPU temperature where `ps5-gpufreq` starts lowering the clock (50–95 °C,
  85 °C by default). It's read at boot, so it saves `ps5_gpufreq.temp_limit` in `cmdline.txt` and
  needs a reboot. Picking 85 °C removes the argument. It asks before saving a value above 85 °C.
- **Micro-stutter Fix**: removes `idle=halt` from `cmdline.txt`, the wiki's first fix for
  micro-stutter. Needs a reboot.
- **Hide Compute Queue** (base PS5 and Slim): writes `AMD_PS5_COMPUTE_QUEUE=0` to
  `/etc/environment.d/90-ps5-compute-queue.conf`, for a game that glitches or hangs with PS5
  Bazzite Deck's Mesa. Applies after logging out and back in.
- **PS5 Pro**: on a Pro the PS5 Pro and Thermal Limit cards come first and CU Unlock is hidden,
  since all 60 CUs are already on. The page shows the active CU count instead. It warns
  when the count is lower or dmesg has no `using Viola firmware` line, which means the Viola firmware
  wasn't loaded. It can also set `AMD_VIOLA_COMPUTE_QUEUE=0` (hide the async compute queue) and
  `RADV_VIOLA_ML=0` (stock int8 path) for every session in `/etc/environment.d/90-ps5-viola.conf`.
  These only work with a Mesa that has the PS5 Pro patches, and you have to log out and back in for
  them to apply. The Pro's GPU clock reads 0 MHz while idle, so the page shows **Idle**.
  The Pro card also warns when dmesg shows `mp1fw_sendmsg: Error : busy` (a kernel whose CPU clock
  driver is too old). **Bluetooth Fix** adds `btusb.ps5_ep_resync=1` to `cmdline.txt` for the
  Pro's MT7925 Bluetooth. Only rmuxnet's kernel has that option, so the toggle stays disabled
  elsewhere. **Save Dump** appears when amdgpu has a crash dump
  (`/sys/class/drm/card*/device/devcoredump/data`) and copies it to your home folder. The Pro
  doesn't recover from GPU faults, and the kernel deletes the dump about 5 minutes after the fault.

- **CU Unlock**: turns on the compute units disabled at the factory (36 or 38 active out of 40). **40
  CUs** adds `amdgpu.ps5_cu_unlock=3` to `cmdline.txt` on the boot drive, and **38 CUs** also adds
  `amdgpu.disable_cu=0.0.0` to mask one pair, so both need a reboot. **Off** removes both arguments,
  including a `disable_cu` you added yourself. The previous file is kept as `cmdline.txt.bak`.
  **Active CUs** shows the count the driver reported. Only an even split across both shader engines
  helps performance, so 38 CUs usually scores the same as 36. Some disabled CUs can be faulty, and
  the pair masked for 38 CUs is always the same one, so it may not avoid them. If you see glitches,
  try `RADV_DEBUG=nohiz`, then turn this off. If the screen is unusable, remove the arguments over
  SSH or from another computer.
- **Apply Now** (experimental): applies a CU Unlock change without a reboot by reloading amdgpu. It
  closes everything on screen and quits this app, so it needs `amdgpu` built as a module and a
  systemd display manager. Without those, only the reboot works. If something else is still using
  the GPU the driver can't unload, and the display comes back with nothing changed. See
  `journalctl -u ps5-hwcon-cu-reload` for what happened.
- **Boot partition**: CU Unlock, Thermal Limit, GPU Memory and zswap edit files on the FAT partition the console booted
  from, wherever the distro or desktop mounted it. If it isn't mounted, the app mounts it read-only
  at `/boot/efi` (or `/run/ps5-hwcon/boot` if that's taken), and only makes it writable while
  saving. It picks the partition whose `cmdline.txt` has the running `root=` argument. If it can't
  find one, or can't tell which one that is, the GPU or Memory page shows why.
GPU governors need a kernel built with `CONFIG_PS5_GPUFREQ`. The driver isn't part of
[ps5-linux-patches](https://github.com/ps5-linux/ps5-linux-patches) itself, so on those kernels the
GPU tab shows why it's unavailable and everything else works normally. While the CPU boosts (3.3–3.5 GHz) the
firmware holds the GPU at 2.23 GHz regardless of these settings.

### Memory

- **Overview**: live RAM and swap usage, including each swap device.
- **GPU Memory**: **VRAM** writes `vram.txt` on the boot drive, in the hex format the loader expects,
  and warns if the existing value looks wrong. It's a minimum that stays reserved from system RAM.
  6 GB is the recommended choice for gaming; pick 512 MB on a desktop or server that doesn't game,
  or enter any size from 0.25 to 12 GB under **Custom**. **GTT Limit** sets `ttm.pages_limit` in
  `cmdline.txt`, which raises how much system RAM the GPU can use without reserving it, so try this
  if a game runs out of memory. Both need a reboot. See the
  [wiki](https://wiki.ps5-linux.eu/post-install/all-distros/#memory-and-swap) for how the two
  interact.
- **zram**: turns compressed swap in RAM on or off and sets its size and compression, by writing
  `/etc/systemd/zram-generator.conf` (the previous file is kept as `.bak`). Needs `zram-generator`
  and a reboot. Turning it off writes a config without a device, which also masks a distro default.
- **zswap**: switches zswap on or off immediately and saves `zswap.enabled` in `cmdline.txt`. It only
  helps with swap on a drive, so leave it off when using zram.
- **Swap File**: creates a 4, 8 or 16 GB swap file at `/swapfile`, turns it on and adds it to
  `/etc/fstab` (the previous fstab is kept as `.bak`). On Btrfs it uses `btrfs filesystem
  mkswapfile`. **Remove** turns it off, deletes it and takes it out of fstab.
- **Swappiness**: sets `vm.swappiness` (0–200) now and saves it in
  `/etc/sysctl.d/90-ps5-hwcon-swappiness.conf`.

### Display

- **HDMI Link** (upstream kernels): the live FRL rate, whether the 4K 120 Hz link failed, Auto Low
  Latency Mode and recovery state, read from `/sys/module/hdmi/parameters`. **Retry 4K 120 Hz**
  tries the fast link again after a failure.
- **Boot Options**: 1080p Safe Mode (`amdgpu.force_1080p=1`), No 4K at 120 Hz (`hdmi.frl_4k120=0`),
  No VRR (`hdmi.vrr=0`), Don't Wake the TV (`ps5_cec.one_touch_play=0`) and Front USB-C Display
  (`usbc_dp.enable=1`). Each one is saved in `cmdline.txt` (the previous file is kept as `.bak`)
  and needs a reboot. Options the running kernel doesn't have are greyed out.

### Warm Reboot

The **Warm Reboot** button at the bottom of the window restarts Linux with `kexec`, skipping the
PS5 OS and the loader. It loads `bzImage`, `initrd.img` and `cmdline.txt` from the boot partition,
so `cmdline.txt` changes apply, but a VRAM change still needs a full start with the loader. It
appears only when `kexec-tools` is installed, and asks before restarting. Warm reboots are
experimental.

On PS5 Bazzite Deck the button uses the image's built-in warm reboot (`ps5-kexec`), which also
works without `kexec-tools` and keeps the PS5 Pro GPU firmware. It doesn't change the
`ps5-warm-reboot on/off` setting. While an update is staged, restart normally once instead.

### LED

- Quick buttons for Off, White Bright, Blue Rich, Purple, Orange Breathe and Pink Breathe.
- A filterable list of every preset the kernel exposes.
- **Active Preset** survives closing and reopening the app. After a reboot it shows Unknown until
  you pick a preset (or Restore on Startup does), because the kernel picks its own default LED.
- **Loop Animations**: replays breathe and pulse animations every 2–30 s, in the background.
- **Restore on Startup**: re-applies your last LED preset when the app starts.

## Single-file builds

GitHub Actions (`.github/workflows/release.yml`) builds `ps5-hwcon-gui-linux-x86_64`, one
executable with Python and Qt bundled, so the PS5 needs no Python or pip. Every push and pull
request builds it and checks that it starts; the file is attached to the run as an artifact.

To publish a release, set `__version__` in `ps5hwcon/__init__.py`, then push a matching tag:

```sh
git tag v1.0.0
git push origin v1.0.0
```

The workflow creates the GitHub release and attaches the binary and its SHA-256 checksum. On the
PS5:

```sh
chmod +x ps5-hwcon-gui-linux-x86_64
sudo -E ./ps5-hwcon-gui-linux-x86_64            # or --tray
```

To build it yourself on Linux x86_64, run `packaging/build_binary.sh` (see the comment at its top).

## Credits

- [NotHavocc/ps5-hwcon-plugin](https://github.com/NotHavocc/ps5-hwcon-plugin), which this is ported
  from. (haha credit to myself)
- [NotHavocc/PinkDesktopPet](https://github.com/NotHavocc/PinkDesktopPet), where the GUI was ported from (haha credit to myself again)
- [rmuxnet/ps5-linux-patches](https://github.com/rmuxnet/ps5-linux-patches-1) for the kernel drivers.
