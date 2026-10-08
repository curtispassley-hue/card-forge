# Updating and removing CardForge Studio

Save your project before updating. Close CardForge, then run the latest **CardForgeStudio-Setup.exe**. Installed releases share one application ID and reuse the existing installation directory and Windows app entry. You do not need to uninstall the previous installed release first. Projects and export folders are user files and are not intentionally removed by the installer.

You can remove an installed version from **Windows Settings → Apps → Installed apps**, the Start menu's **Uninstall CardForge Studio** shortcut, or **Menu → Updates / uninstall** in CardForge. Save your work first. The uninstaller removes the installed program; keep your editable `.cardforge` files and export folders separately.

Older portable ZIP versions are separate extracted folders and do not have a registered uninstaller. Save or copy any projects/exports you placed inside an old folder before removing that folder yourself. CardForge does not search your drive and delete older portable copies. Launch the current installed shortcut to avoid accidentally opening an older portable EXE.

Portable releases must retain their `_internal` folder alongside CardForge4D.exe. Do not move only the executable. Use the installer if you prefer one installed version and an automatic uninstaller.

The installer includes a release-candidate number in Windows Installed apps. This is still an unsigned release candidate. Leave virus protection enabled.

Installer update behavior follows [Inno Setup's same-application rules](https://jrsoftware.org/ishelp/topic_sameappnotes.htm). Release checks test upgrading from RC19, retaining a user project file, running the installed app, and uninstalling.
