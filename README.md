# PyAutoActions

PyAutoActions automates HDR management for your games and applications, enabling and disabling HDR based on the process status. It's designed to work seamlessly with low system impact and integrates perfectly with [ForceAutoHDR](https://github.com/7gxycn08/ForceAutoHDR) for enhanced compatibility.

## Features

- **Automatic HDR Toggle**: Automatically enables HDR when a game/app starts and disables it upon closure.
- **Automatic Refresh Rate Switching Toggle**: Automatically changes monitors Refresh Rate when a game/app starts and reverts Refresh Rate to previous value upon closure.
- **Low System Impact**: Operates efficiently using only 3 threads and minimal CPU usage.
- **Tray Functionality**: Resides in the system tray for easy access and minimal interference.
- **Game Launcher**: Launch games directly from the system tray to ensure HDR settings are correctly applied.
- **Compatibility**: Works in tandem with ForceAutoHDR for games not officially supported by AutoHDR.

<img width="677" height="484" alt="135" src="https://github.com/user-attachments/assets/e7c2837e-058d-46c9-9bd7-c158c423dba8" />

<img width="187" height="137" alt="135tray" src="https://github.com/user-attachments/assets/e63c40fe-cbc5-4db3-afce-6b087f44c310" />

## Refresh Rate Switching
- **`Enable Refresh Rate Switching` when toggled on user will be asked to enter target refresh value everytime user adds a new exe.**
- **Monitor refresh rate will change to target value upon process start and return to previous value on process exit.**

## Monitor Selection

- **`All Monitors` will apply hdr/sdr switching globally on all monitors.**
- **`Primary Monitor` will apply hdr/sdr switching on primary monitor only.**

## Detection Settings

- **Adjustable**: Choose from `High`, `Medium`, or `Low` for adjusting the speed of HDR switching. `Low` is the fastest at the expence of extra cpu usage default is `High`.
- **User Preferences**: Settings are saved and automatically applied on application restart.

## Toggle Mode Settings

- **`SDR To HDR`: Will `enable` HDR at game start and `disable` HDR when the game closes.**
- **`HDR To SDR`: Will `disable` HDR at game start and `enable` HDR when the game closes.**

## Getting Started


![winget](https://github.com/7gxycn08/ForceAutoHDR/assets/121936658/4dd2df30-da47-4dcd-9219-396709fa6f3b)

To start using PyAutoActions, download the latest release from our [Releases page](https://github.com/7gxycn08/PyAutoActions/releases). Install it using the setup file and run the application.

Alternatively you can install and update via [Windows Package Manager (Winget)](https://docs.microsoft.com/en-us/windows/package-manager/winget/):


`winget install 7gxycn08.PyAutoActions`

1. **Add Games**: Use the GUI to add the executable path of your games.
2. **Automatic HDR Management**: HDR will enable when a game/app starts and disable upon its closure.
3. **Startup Option**: Enable running PyAutoActions at system boot via the tray icon context menu.
4. **Enhanced Compatibility**: Use [ForceAutoHDR](https://github.com/7gxycn08/ForceAutoHDR) for AutoHDR in unsupported games.
5. **Pre-Launch HDR Activation**: Launch games/apps from the system tray to ensure HDR is enabled beforehand when games require HDR to be enabled before launch.

## Latest Changes

- Added Windows 11 24H2 support
- Updated Python to v3.13.9
- Fixed issue where hdr won't turn on for Nvidia GPU's
- Added new feature Refresh Rate Switching per exe under file menu in gui enabled by default

## Contributing

Your contributions make PyAutoActions better! We welcome pull requests, feature requests, and any other contributions. If you're looking to add new features or improve existing ones, please feel free to contribute.

## TODO

- Explore additional functionalities.
- Encourage community contributions and feature requests.

## Copy Right

Copyright 2026 7gxycn08@github.com

Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
