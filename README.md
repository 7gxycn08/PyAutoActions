# PyAutoActions

PyAutoActions automates HDR management for your games and applications, enabling and disabling HDR based on the process status. It's designed to work seamlessly with low system impact and integrates perfectly with [ForceAutoHDR](https://github.com/7gxycn08/ForceAutoHDR) for enhanced compatibility.

## Features

- **Automatic HDR Toggle**: Automatically enables HDR when a game starts and disables it upon closure.
- **Low System Impact**: Operates efficiently using only 3 threads and minimal CPU usage.
- **Tray Functionality**: Resides in the system tray for easy access and minimal interference.
- **Game Launcher**: Launch games directly from the system tray to ensure HDR settings are correctly applied.
- **Compatibility**: Works in tandem with ForceAutoHDR for games not officially supported by AutoHDR.

![1 2 4](https://github.com/user-attachments/assets/2ba64a3f-289d-406a-898a-700a3f5a638a)

![System Tray Example](https://github.com/user-attachments/assets/9022fb66-ce10-45cd-9b81-454cc707de53)

## Monitor Selection

- **`All Monitors` will apply hdr/sdr switching globally on all monitors.**
- **`Primary Monitor` will apply hdr/sdr switching on primary monitor only.**

## Detection Settings

- **Adjustable**: Choose from `High`, `Medium`, or `Low` for adjusting the speed of HDR switching. `Low` is the fastest at the expence of extra cpu usage default is `High`.
- **User Preferences**: Settings are saved and automatically applied on application restart.

## Toggle Mode Settings

- **`SDR To HDR`: Will `enable` HDR at game start and `disable` HDR when the game closes.**
- **`HDR To SDR`: Will `disable` HDR at game start and `enable` HDR when the game closes.**
- **`Respect Global Settings`: Will detect if system HDR is on or off at game start and adjust accordingly.**

## Getting Started

1. **Add Games**: Use the GUI to add the executable path of your games.
2. **Automatic HDR Management**: HDR will enable when a game starts and disable upon its closure.
3. **Startup Option**: Enable running PyAutoActions at system boot via the tray icon context menu.
4. **Enhanced Compatibility**: Use [ForceAutoHDR](https://github.com/7gxycn08/ForceAutoHDR) for AutoHDR in unsupported games.
5. **Pre-Launch HDR Activation**: Launch games from the system tray to ensure HDR is enabled beforehand when games require HDR to be enabled before launch.

## Latest Changes

- Added multi-monitor support.
  

## Contributing

Your contributions make PyAutoActions better! We welcome pull requests, feature requests, and any other contributions. If you're looking to add new features or improve existing ones, please feel free to contribute.

## TODO

- Explore additional functionalities.
- Encourage community contributions and feature requests.

